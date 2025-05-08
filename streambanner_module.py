import discord
import os
import asyncio
import logging
import json
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
from datetime import datetime, timezone
from discord import app_commands
from discord.ext import commands
from discord.ui import Button, View, Modal, TextInput, Select

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

DEPENDENCIES = []
MODULE_PATH = "modules/streambanner"
TEMP_PATH = f"{MODULE_PATH}/zwischenspeicher"
IMAGE_PATH = f"{MODULE_PATH}/Streambanner.png"
FONT_PATH = f"{MODULE_PATH}/font.ttf"
CSS_PATH = f"{MODULE_PATH}/styles.css"
SPIELMODI_PATH = f"{MODULE_PATH}/spielmodi"

class StyleManager:
    def __init__(self, css_path: str):
        self.css_path = css_path
        self.styles = self._load_styles()
        
    def _load_styles(self) -> dict:
        try:
            if os.path.exists(self.css_path):
                with open(self.css_path, 'r', encoding='utf-8') as f:
                    loaded_styles = json.load(f)
                    if self._validate_styles(loaded_styles):
                        logging.info("✅ CSS-Styles erfolgreich geladen")
                        return loaded_styles
            logging.warning("⚠️ Keine gültige CSS-Datei gefunden, erstelle Standard-Styles")
            return self._create_default_styles()
        except Exception as e:
            logging.error(f"❌ Fehler beim Laden der CSS-Datei: {str(e)}")
            return self._create_default_styles()
            
    def _validate_styles(self, styles: dict) -> bool:
        required_elements = ['text1', 'text2']
        required_properties = {
            'text1': ['position', 'size', 'color', 'align'],
            'text2': ['position', 'size', 'color', 'align']
        }
        try:
            for element in required_elements:
                if element not in styles:
                    logging.warning(f"⚠️ Fehlendes Element in CSS: {element}")
                    return False
                element_style = styles[element]
                for prop in required_properties[element]:
                    if prop not in element_style:
                        logging.warning(f"⚠️ Fehlende Eigenschaft in {element}: {prop}")
                        return False
            return True
        except Exception as e:
            logging.error(f"❌ Fehler bei der Style-Validierung: {str(e)}")
            return False

    def _create_default_styles(self) -> dict:
        default_styles = {
            "text1": {
                "position": { "x": 256, "y": 500 },
                "size": 70,
                "color": "#ffffff",
                "align": "center"
            },
            "text2": {
                "position": { "x": 768, "y": 500 },
                "size": 70,
                "color": "#ffffff",
                "align": "center"
            }
        }
        os.makedirs(os.path.dirname(self.css_path), exist_ok=True)
        try:
            with open(self.css_path, 'w', encoding='utf-8') as f:
                json.dump(default_styles, f, indent=4)
                logging.info(f"✅ Standardstyles wurden in '{self.css_path}' gespeichert.")
        except Exception as e:
            logging.error(f"❌ Fehler beim Erstellen der CSS-Datei: {str(e)}")
        return default_styles
            
    def get_style(self, element_id: str) -> dict:
        style = self.styles.get(element_id, {})
        if not style:
            self.reload()
            style = self.styles.get(element_id, {})
        return style
        
    def reload(self) -> bool:
        try:
            self.styles = self._load_styles()
            return True
        except Exception as e:
            logging.error(f"❌ Fehler beim Neuladen der Styles: {str(e)}")
            return False

class TeamNameModal(Modal):
    def __init__(self, team_type: str):
        super().__init__(title=f"{team_type} Namen eingeben")
        self.team_type = team_type
        self.team_name = TextInput(
            label=f"{team_type} Name",
            placeholder=f"Gib den Namen des {team_type}s ein",
            required=True,
            max_length=50
        )
        self.add_item(self.team_name)
        
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        return self.team_name.value.upper()

class TextSizeModal(Modal):
    def __init__(self):
        super().__init__(title="Textgröße anpassen")
        self.text_size = TextInput(
            label="Textgröße für beide Texte",
            placeholder="Gib eine Zahl ein, z.B. 70",
            default="70",
            required=True,
            max_length=3
        )
        self.add_item(self.text_size)
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            size = int(self.text_size.value.strip())
        except ValueError:
            size = 70
        self.value = size

class SpielmodusSelect(Select):
    def __init__(self):
        options = []
        if os.path.exists(SPIELMODI_PATH):
            for filename in os.listdir(SPIELMODI_PATH):
                if filename.lower().endswith(".png"):
                    name = os.path.splitext(filename)[0].upper()
                    options.append(discord.SelectOption(label=name, value=name))
            options.sort(key=lambda opt: opt.label)
        if not options:
            options.append(discord.SelectOption(label="KEINE OPTION", value=""))
        super().__init__(placeholder="Wähle den Spielmodus", min_values=1, max_values=1, options=options)
    
    async def callback(self, interaction: discord.Interaction):
        self.view.spielmodus = self.values[0]
        embed = discord.Embed(
            title="✅ Spielmodus gewählt",
            description=f"Ausgewählter Spielmodus: **{self.values[0]}**",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

class StreambannerView(View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog
        self.bot = cog.bot
        self.home_team_name = None
        self.away_team_name = None
        self.spielmodus = None
        self.text_size = None  
        self.command_message = None
        self.start_time = datetime.now(timezone.utc)
        
        # Verwende das emoji-Feld, damit die Emojis größer dargestellt werden.
        self.add_item(Button(style=discord.ButtonStyle.primary, label="Heim Team", emoji="🏠", custom_id="home_team"))
        self.add_item(Button(style=discord.ButtonStyle.danger, label="Auswärts Team", emoji="✈️", custom_id="away_team"))
        self.add_item(SpielmodusSelect())
        self.add_item(Button(style=discord.ButtonStyle.secondary, label="Textgröße", emoji="📏", custom_id="text_size_button"))
        self.add_item(Button(style=discord.ButtonStyle.secondary, label="Vorschau", emoji="👁️", custom_id="preview"))
        self.add_item(Button(style=discord.ButtonStyle.primary, label="Erstellen", emoji="✅", custom_id="create"))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        button_id = interaction.data.get("custom_id")
        if not self.command_message:
            async for message in interaction.channel.history(limit=100):
                if message.content and message.content.lower().startswith('/streambanner'):
                    self.command_message = message
                    self.start_time = message.created_at.replace(tzinfo=timezone.utc)
                    break
        
        if button_id == "home_team":
            await self.home_team_button(interaction)
        elif button_id == "away_team":
            await self.away_team_button(interaction)
        elif button_id == "text_size_button":
            await self.text_size_button(interaction)
        elif button_id == "preview":
            await self.preview_button(interaction)
        elif button_id == "create":
            await self.create_button(interaction)
        return True

    async def home_team_button(self, interaction: discord.Interaction):
        modal = TeamNameModal("Heim Team")
        await interaction.response.send_modal(modal)
        await modal.wait()
        self.home_team_name = modal.team_name.value.upper()
        embed = discord.Embed(
            title="✅ Heim Team gesetzt",
            description=f"Dein Heim Team-Name **{self.home_team_name}** wurde erfolgreich gespeichert.",
            color=discord.Color.green()
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    async def away_team_button(self, interaction: discord.Interaction):
        modal = TeamNameModal("Auswärts Team")
        await interaction.response.send_modal(modal)
        await modal.wait()
        self.away_team_name = modal.team_name.value.upper()
        embed = discord.Embed(
            title="✅ Auswärts Team gesetzt",
            description=f"Dein Auswärts Team-Name **{self.away_team_name}** wurde erfolgreich gespeichert.",
            color=discord.Color.green()
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
    
    async def text_size_button(self, interaction: discord.Interaction):
        modal = TextSizeModal()
        await interaction.response.send_modal(modal)
        await modal.wait()
        self.text_size = modal.value
        embed = discord.Embed(
            title="✅ Textgröße gesetzt",
            description=f"Die Textgröße für beide Texte wurde auf **{self.text_size}** gesetzt.",
            color=discord.Color.green()
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
            
    async def preview_button(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not all([self.home_team_name, self.away_team_name, self.spielmodus]):
            embed = discord.Embed(
                title="⚠️ Unvollständige Daten",
                description="Bitte setze zuerst beide Team-Namen und wähle einen Spielmodus aus.",
                color=discord.Color.orange()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        try:
            preview_path = await self.cog.generate_streambanner_image(
                interaction.user.id,
                self.home_team_name,
                self.away_team_name,
                self.spielmodus,
                text_size=self.text_size,
                preview=True
            )
            with open(preview_path, 'rb') as f:
                file = discord.File(f, filename="streambanner_preview.png")
            embed = discord.Embed(
                title="👁️ Vorschau deines Streambanners",
                color=discord.Color.blue()
            )
            embed.set_image(url="attachment://streambanner_preview.png")
            preview_msg = await interaction.followup.send(embed=embed, file=file, ephemeral=True)
            await asyncio.sleep(30)
            try:
                await preview_msg.delete()
            except:
                pass
            self.cog.clear_temp_files()
        except Exception as e:
            logging.error(f"❌ Fehler bei der Vorschau: {str(e)}")
            embed = discord.Embed(
                title="❌ Fehler bei der Vorschau",
                description=f"Bei der Erstellung der Vorschau ist ein Fehler aufgetreten: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

    async def create_button(self, interaction: discord.Interaction):
        await interaction.response.defer()
        missing_data = []
        if not self.home_team_name:
            missing_data.append("Heim-Team Name")
        if not self.away_team_name:
            missing_data.append("Auswärts-Team Name")
        if not self.spielmodus:
            missing_data.append("Spielmodus Auswahl")
        if missing_data:
            embed = discord.Embed(
                title="⚠️ Unvollständige Daten",
                description=f"Folgende Informationen fehlen: {', '.join(missing_data)}",
                color=discord.Color.orange()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        try:
            final_path = await self.cog.generate_streambanner_image(
                interaction.user.id,
                self.home_team_name,
                self.away_team_name,
                self.spielmodus,
                text_size=self.text_size
            )
            with open(final_path, 'rb') as f:
                file = discord.File(f, filename="streambanner_final.png")
            title_text = f"{self.home_team_name} vs {self.away_team_name}"
            embed = discord.Embed(
                title=title_text,
                description=f"Spielmodus: **{self.spielmodus}**",
                color=discord.Color.gold()
            )
            embed.set_image(url="attachment://streambanner_final.png")
            embed.set_footer(text=f"Erstellt von {interaction.user.name}")
            final_message = await interaction.followup.send(embed=embed, file=file)
            await asyncio.sleep(1)
            try:
                messages = []
                async for message in interaction.channel.history(limit=100):
                    if message.id == final_message.id:
                        continue
                    if (message.content and message.content.lower().startswith('/streambanner') or
                        (message.created_at.replace(tzinfo=timezone.utc) >= self.start_time and 
                         (message.author == self.bot.user or message.author == interaction.user))):
                        messages.append(message)
                if messages:
                    await interaction.channel.delete_messages(messages)
            except Exception as e:
                logging.error(f"❌ Fehler beim Löschen der Nachrichten: {str(e)}")
            self.cog.clear_temp_files()
        except Exception as e:
            logging.error(f"❌ Fehler beim Erstellen des Streambanners: {str(e)}")
            embed = discord.Embed(
                title="❌ Fehler beim Erstellen",
                description=f"Fehler: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

class Streambanner(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.style_manager = StyleManager(CSS_PATH)
        self.create_directories()
        
    def create_directories(self):
        os.makedirs(MODULE_PATH, exist_ok=True)
        os.makedirs(TEMP_PATH, exist_ok=True)
        os.makedirs(SPIELMODI_PATH, exist_ok=True)
        if not os.path.exists(IMAGE_PATH):
            logging.warning(f"⚠️ Streambanner-Basisbild nicht gefunden unter '{IMAGE_PATH}'.")
            self.create_default_image()
        if not os.path.exists(FONT_PATH):
            logging.warning(f"⚠️ Schriftart nicht gefunden unter '{FONT_PATH}'.")
            self.create_default_font()

    def create_default_image(self):
        try:
            img = Image.new('RGBA', (1920, 1080), color=(41, 41, 41, 0))
            draw = ImageDraw.Draw(img)
            try:
                font = ImageFont.truetype(FONT_PATH, 48)
            except:
                font = ImageFont.load_default()
            draw.text((960, 100), "STREAMBANNER", fill=(255, 255, 255, 255), font=font, anchor="mm")
            img.save(IMAGE_PATH)
            logging.info(f"✅ Standard-Streambanner wurde unter '{IMAGE_PATH}' erstellt.")
        except Exception as e:
            logging.error(f"❌ Fehler beim Erstellen des Standard-Streambanners: {str(e)}")
            
    def create_default_font(self):
        try:
            with open(FONT_PATH, 'wb') as f:
                pass
            logging.warning(f"⚠️ Platzhalter für Schriftart erstellt unter '{FONT_PATH}'.")
            logging.warning("Bitte füge eine TrueType-Schriftart (.ttf) an diesem Speicherort hinzu.")
        except Exception as e:
            logging.error(f"❌ Fehler beim Erstellen des Schriftart-Platzhalters: {str(e)}")

    def clear_temp_files(self, user_id: int = None):
        try:
            if not os.path.exists(TEMP_PATH):
                return
            for filename in os.listdir(TEMP_PATH):
                file_path = os.path.join(TEMP_PATH, filename)
                if os.path.isfile(file_path):
                    os.remove(file_path)
        except Exception as e:
            logging.error(f"❌ Fehler beim Löschen temporärer Dateien: {str(e)}")

    async def generate_streambanner_image(self, user_id, home_name, away_name, spielmodus, text_size=None, preview=False):
        try:
            base_img = Image.open(IMAGE_PATH).convert("RGBA")
            base_img = base_img.resize((1920, 1080), Image.Resampling.LANCZOS)
            text1_style = self.style_manager.get_style('text1')
            text2_style = self.style_manager.get_style('text2')
            if text_size is not None:
                text1_style['size'] = text_size
                text2_style['size'] = text_size
            draw = ImageDraw.Draw(base_img)
            try:
                font_home = ImageFont.truetype(FONT_PATH, text1_style.get('size', 70))
                font_away = ImageFont.truetype(FONT_PATH, text2_style.get('size', 70))
            except Exception as e:
                logging.warning(f"Konnte Schriftart nicht laden: {str(e)}")
                font_home = font_away = ImageFont.load_default()
            if home_name:
                pos_home = (
                    text1_style.get('position', {}).get('x', 256),
                    text1_style.get('position', {}).get('y', 500)
                )
                draw.text(pos_home, home_name.upper(),
                         fill=text1_style.get('color', "#ffffff"),
                         font=font_home, anchor="mm")
            if away_name:
                pos_away = (
                    text2_style.get('position', {}).get('x', 768),
                    text2_style.get('position', {}).get('y', 500)
                )
                draw.text(pos_away, away_name.upper(),
                         fill=text2_style.get('color', "#ffffff"),
                         font=font_away, anchor="mm")
            if spielmodus and isinstance(spielmodus, str) and spielmodus.strip():
                spielmodus_filename = f"{SPIELMODI_PATH}/{spielmodus}.png"
                if os.path.exists(spielmodus_filename):
                    try:
                        spielmodus_img = Image.open(spielmodus_filename).convert("RGBA")
                        spielmodus_img = spielmodus_img.resize((base_img.width, base_img.height), Image.Resampling.LANCZOS)
                        base_img = Image.alpha_composite(base_img, spielmodus_img)
                    except Exception as e:
                        logging.error(f"Fehler beim Verarbeiten des Spielmodus-Bildes: {str(e)}")
                else:
                    logging.error(f"Spielmodus-Bild nicht gefunden: {spielmodus_filename}")
            suffix = "_preview" if preview else "_final"
            output_path = f"{TEMP_PATH}/streambanner_{user_id}{suffix}.png"
            base_img.save(output_path, 'PNG', quality=95)
            return output_path
        except Exception as e:
            logging.error(f"❌ Fehler beim Generieren des Streambanners: {str(e)}")
            raise

    @app_commands.command(name="streambanner", description="Erstellt ein Streambanner mit Team-Namen und Spielmodus")
    async def streambanner_command(self, interaction: discord.Interaction):
        if not os.path.exists(IMAGE_PATH):
            self.create_default_image()
        if not os.path.exists(FONT_PATH):
            self.create_default_font()
            embed = discord.Embed(
                title="⚠️ Schriftart fehlt",
                description=f"Bitte füge eine TrueType-Schriftart (.ttf) unter `{FONT_PATH}` hinzu.",
                color=discord.Color.orange()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        embed = discord.Embed(
            title="🎮 Streambanner erstellen",
            description=(
                "Erstelle ein Streambanner mit den Team-Namen und einem ausgewählten Spielmodus.\n\n"
                "**Anleitung:**\n"
                "1. 🏠 **Heim Team**: Namen eingeben\n"
                "2. ✈️ **Auswärts Team**: Namen eingeben\n"
                "3. 🎮 **Spielmodus**: Wähle den gewünschten Spielmodus aus dem Dropdown Menü\n"
                "4. 📏 **Textgröße**: Passe die Größe beider Texte an (Standard: 70)\n"
                "5. 👁️ **Vorschau**: Zeigt eine Vorschau deines Banners\n"
                "6. ✅ **Erstellen**: Erstellt das finale Banner"
            ),
            color=discord.Color.blue()
        )
        view = StreambannerView(self)
        await interaction.response.send_message(embed=embed, view=view)
        original_message = await interaction.original_response()
        view.command_message = original_message
        view.start_time = original_message.created_at.replace(tzinfo=timezone.utc)

async def setup(bot):
    os.makedirs(MODULE_PATH, exist_ok=True)
    await bot.add_cog(Streambanner(bot))
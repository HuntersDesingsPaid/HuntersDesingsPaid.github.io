import discord
import os
import asyncio
import logging
import json
import shutil
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
from datetime import datetime, timezone, timedelta
from discord import app_commands
from discord.ext import commands
from discord.ui import Button, View, Modal, TextInput
from typing import Dict, List, Optional, Any, Union, Callable

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

DEPENDENCIES = []
MODULE_PATH = "modules/matchday"
TEMP_PATH = f"{MODULE_PATH}/zwischenspeicher"
IMAGE_PATH = f"{MODULE_PATH}/matchday.png"
FONT_PATH = f"{MODULE_PATH}/font.ttf"
CSS_PATH = f"{MODULE_PATH}/styles.css"

class StyleManager:
    def __init__(self, css_path: str):
        self.css_path = css_path
        self.styles = self._load_styles()
        
    def _load_styles(self) -> Dict[str, Any]:
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
            
    def _validate_styles(self, styles: Dict[str, Any]) -> bool:
        required_elements = ['logo1', 'logo2', 'text1', 'text2', 'text3']
        required_properties = {
            'logo1': ['position', 'size'],
            'logo2': ['position', 'size'],
            'text1': ['position', 'size', 'color', 'align'],
            'text2': ['position', 'size', 'color', 'align'],
            'text3': ['position', 'size', 'color', 'align']
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

    def _create_default_styles(self) -> Dict[str, Any]:
        default_styles = {
            "logo1": {"position": {"x": 256, "y": 300}, "size": {"width": 256, "height": 256}},
            "text1": {"position": {"x": 256, "y": 500}, "size": 36, "color": "#ffffff", "align": "center"},
            "logo2": {"position": {"x": 768, "y": 300}, "size": {"width": 256, "height": 256}},
            "text2": {"position": {"x": 768, "y": 500}, "size": 36, "color": "#ffffff", "align": "center"},
            "text3": {"position": {"x": 512, "y": 700}, "size": 48, "color": "#ffffff", "align": "center"}
        }
        os.makedirs(os.path.dirname(self.css_path), exist_ok=True)
        try:
            with open(self.css_path, 'w', encoding='utf-8') as f:
                json.dump(default_styles, f, indent=4)
                logging.info(f"✅ Standardstyles wurden in '{self.css_path}' gespeichert.")
        except Exception as e:
            logging.error(f"❌ Fehler beim Erstellen der CSS-Datei: {str(e)}")
        return default_styles
            
    def get_style(self, element_id: str) -> Dict[str, Any]:
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

class PostInfoModal(Modal):
    def __init__(self):
        super().__init__(title="Postinfo eingeben")
        current_time = datetime.now(timezone.utc)
        formatted_time = (current_time + timedelta(hours=1)).strftime("%H:%M")
        
        self.info = TextInput(
            label="Postinfo",
            placeholder="z.B. Live auf Twitch.tv/username",
            default=f"AB {formatted_time} LIVE AUF TWITCH.TV/ZEALOXGAMING",
            required=True,
            max_length=100
        )
        self.add_item(self.info)
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        self.value = self.info.value.strip().upper()

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        await interaction.response.send_message("Ein Fehler ist aufgetreten. Bitte versuche es erneut.", ephemeral=True)

class MatchdayView(View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog
        self.bot = cog.bot
        self.home_team_logo = None
        self.away_team_logo = None
        self.home_team_name = None
        self.away_team_name = None
        self.post_info = None
        self.command_message = None
        self.start_time = datetime.now(timezone.utc)
        
        self.add_item(Button(style=discord.ButtonStyle.primary, label="Heim Team", custom_id="home_team", emoji="🏠"))
        self.add_item(Button(style=discord.ButtonStyle.danger, label="Auswärts Team", custom_id="away_team", emoji="✈️"))
        self.add_item(Button(style=discord.ButtonStyle.success, label="Postinfo", custom_id="post_info", emoji="📝"))
        self.add_item(Button(style=discord.ButtonStyle.secondary, label="Vorschau", custom_id="preview", emoji="👁️"))
        self.add_item(Button(style=discord.ButtonStyle.primary, label="Erstellen", custom_id="create", emoji="✅"))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        button_id = interaction.data["custom_id"]
        if not self.command_message:
            async for message in interaction.channel.history(limit=100):
                if message.content and message.content.lower().startswith('/matchday'):
                    self.command_message = message
                    self.start_time = message.created_at.replace(tzinfo=timezone.utc)
                    break
        
        if button_id == "home_team":
            await self.home_team_button(interaction)
        elif button_id == "away_team":
            await self.away_team_button(interaction)
        elif button_id == "post_info":
            await self.post_info_button(interaction)
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
            title="🏠 Heim Team Logo hochladen",
            description="Bitte lade jetzt das Logo des Heimteams hoch (als Antwort auf diese Nachricht).",
            color=discord.Color.blue()
        )
        msg = await interaction.followup.send(embed=embed, silent=True)
        
        def check(m):
            return m.author.id == interaction.user.id and m.channel.id == interaction.channel.id and len(m.attachments) > 0
            
        try:
            message = await interaction.client.wait_for('message', check=check, timeout=60.0)
            
            attachment = message.attachments[0]
            image_data = await attachment.read()
            
            os.makedirs(TEMP_PATH, exist_ok=True)
            
            logo_path = f"{TEMP_PATH}/home_logo_{interaction.user.id}.png"
            with open(logo_path, 'wb') as f:
                f.write(image_data)
                
            self.home_team_logo = logo_path
            
            await message.delete()
            
            embed = discord.Embed(
                title="✅ Heim Team eingerichtet",
                description=f"**Team-Name:** {self.home_team_name}\n**Logo:** Erfolgreich hochgeladen",
                color=discord.Color.green()
            )
            await msg.delete()
            await interaction.followup.send(embed=embed, silent=True)
            
        except asyncio.TimeoutError:
            embed = discord.Embed(
                title="⏱️ Zeit abgelaufen",
                description="Du hast kein Logo innerhalb der Zeitbegrenzung hochgeladen.",
                color=discord.Color.red()
            )
            await msg.delete()
            await interaction.followup.send(embed=embed, silent=True)

    async def away_team_button(self, interaction: discord.Interaction):
        modal = TeamNameModal("Auswärts Team")
        await interaction.response.send_modal(modal)
        await modal.wait()
        
        self.away_team_name = modal.team_name.value.upper()
        
        embed = discord.Embed(
            title="✈️ Auswärts Team Logo hochladen",
            description="Bitte lade jetzt das Logo des Auswärtsteams hoch (als Antwort auf diese Nachricht).",
            color=discord.Color.red()
        )
        msg = await interaction.followup.send(embed=embed, silent=True)
        
        def check(m):
            return m.author.id == interaction.user.id and m.channel.id == interaction.channel.id and len(m.attachments) > 0
            
        try:
            message = await interaction.client.wait_for('message', check=check, timeout=60.0)
            
            attachment = message.attachments[0]
            image_data = await attachment.read()
            
            os.makedirs(TEMP_PATH, exist_ok=True)
            
            logo_path = f"{TEMP_PATH}/away_logo_{interaction.user.id}.png"
            with open(logo_path, 'wb') as f:
                f.write(image_data)
                
            self.away_team_logo = logo_path
            
            await message.delete()
            
            embed = discord.Embed(
                title="✅ Auswärts Team eingerichtet",
                description=f"**Team-Name:** {self.away_team_name}\n**Logo:** Erfolgreich hochgeladen",
                color=discord.Color.green()
            )
            await msg.delete()
            await interaction.followup.send(embed=embed, silent=True)
            
        except asyncio.TimeoutError:
            embed = discord.Embed(
                title="⏱️ Zeit abgelaufen",
                description="Du hast kein Logo innerhalb der Zeitbegrenzung hochgeladen.",
                color=discord.Color.red()
            )
            await msg.delete()
            await interaction.followup.send(embed=embed, silent=True)
            
    async def post_info_button(self, interaction: discord.Interaction):
        try:
            modal = PostInfoModal()
            await interaction.response.send_modal(modal)
            
            await modal.wait()
            
            if hasattr(modal, 'value') and modal.value:
                self.post_info = modal.value
                embed = discord.Embed(
                    title="✅ Postinfo hinzugefügt",
                    description=(
                        "**Die folgenden Informationen wurden gespeichert:**\n"
                        f"```\n{self.post_info}\n```\n"
                        "*Diese Information wird unter den Teams auf dem Matchday-Bild angezeigt.*"
                    ),
                    color=discord.Color.green()
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                self.post_info = None
                embed = discord.Embed(
                    title="❌ Fehler",
                    description="Es wurde keine Information eingegeben.",
                    color=discord.Color.red()
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            logging.error(f"❌ Fehler bei der Postinfo-Verarbeitung: {str(e)}")
            self.post_info = None
            embed = discord.Embed(
                title="❌ Fehler",
                description="Bei der Verarbeitung der Postinfo ist ein Fehler aufgetreten.",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

    async def preview_button(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        if not all([self.home_team_logo, self.away_team_logo, self.home_team_name, self.away_team_name]):
            embed = discord.Embed(
                title="⚠️ Unvollständige Daten",
                description="Es fehlen noch einige Informationen. Bitte fülle zuerst alle Team-Informationen aus.",
                color=discord.Color.orange()
            )
            await interaction.followup.send(embed=embed, silent=True)
            return
            
        try:
            preview_path = await self.cog.generate_matchday_image(
                interaction.user.id,
                self.home_team_logo,
                self.away_team_logo,
                self.home_team_name,
                self.away_team_name,
                self.post_info,
                preview=True
            )
            
            with open(preview_path, 'rb') as f:
                file = discord.File(f, filename="matchday_preview.png")
                
            embed = discord.Embed(
                title="👁️ Vorschau deiner Matchday-Ankündigung",
                color=discord.Color.blue()
            )
            embed.set_image(url="attachment://matchday_preview.png")
            
            preview_msg = await interaction.followup.send(embed=embed, file=file, silent=True)
            
            await asyncio.sleep(30)
            try:
                await preview_msg.delete()
            except:
                pass
            
        except Exception as e:
            logging.error(f"❌ Fehler bei der Vorschau: {str(e)}")
            embed = discord.Embed(
                title="❌ Fehler bei der Vorschau",
                description=f"Bei der Erstellung der Vorschau ist ein Fehler aufgetreten: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, silent=True)

    async def create_button(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        missing_data = []
        if not self.home_team_logo:
            missing_data.append("Heim-Team Logo")
        if not self.home_team_name:
            missing_data.append("Heim-Team Name")
        if not self.away_team_logo:
            missing_data.append("Auswärts-Team Logo")
        if not self.away_team_name:
            missing_data.append("Auswärts-Team Name")
            
        if missing_data:
            embed = discord.Embed(
                title="⚠️ Unvollständige Daten",
                description=f"Es fehlen noch folgende Informationen: {', '.join(missing_data)}",
                color=discord.Color.orange()
            )
            await interaction.followup.send(embed=embed, silent=True)
            return
            
        try:
            final_path = await self.cog.generate_matchday_image(
                interaction.user.id,
                self.home_team_logo,
                self.away_team_logo,
                self.home_team_name,
                self.away_team_name,
                self.post_info
            )
            
            with open(final_path, 'rb') as f:
                file = discord.File(f, filename="matchday_announcement.png")
                
            vs_text = "🔥 **MATCHDAY** 🔥"
            if self.post_info:
                vs_text += f"\n📝 {self.post_info}"
                
            embed = discord.Embed(
                title=f"{self.home_team_name} vs {self.away_team_name}",
                description=vs_text,
                color=discord.Color.gold()
            )
            embed.set_image(url="attachment://matchday_announcement.png")
            embed.set_footer(text=f"Erstellt von {interaction.user.name}")
            
            final_message = await interaction.followup.send(embed=embed, file=file)
            
            await asyncio.sleep(1)
            
            try:
                messages = []
                async for message in interaction.channel.history(limit=100):
                    if message.id == final_message.id:
                        continue
                        
                    if (message.content and message.content.lower().startswith('/matchday') or
                        (message.created_at.replace(tzinfo=timezone.utc) >= self.start_time and 
                         (message.author == self.bot.user or message.author == interaction.user))):
                        messages.append(message)
                
                if messages:
                    await interaction.channel.delete_messages(messages)
                    
            except Exception as e:
                logging.error(f"❌ Fehler beim Löschen der Nachrichten: {str(e)}")
            
            self.cog.clear_temp_files(interaction.user.id)
            
        except Exception as e:
            logging.error(f"❌ Fehler beim Erstellen des Matchday-Bildes: {str(e)}")
            embed = discord.Embed(
                title="❌ Fehler beim Erstellen",
                description=f"Bei der Erstellung des Matchday-Bildes ist ein Fehler aufgetreten: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, silent=True)

class Matchday(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.style_manager = StyleManager(CSS_PATH)
        self.create_directories()
        
    def create_directories(self):
        os.makedirs(MODULE_PATH, exist_ok=True)
        os.makedirs(TEMP_PATH, exist_ok=True)
        
        if not os.path.exists(IMAGE_PATH):
            logging.warning(f"⚠️ Matchday-Grundlagenbild nicht gefunden unter '{IMAGE_PATH}'.")
            self.create_default_image()
            
        if not os.path.exists(FONT_PATH):
            logging.warning(f"⚠️ Schriftart nicht gefunden unter '{FONT_PATH}'.")
            self.create_default_font()

    def create_default_image(self):
        try:
            img = Image.new('RGB', (1024, 1024), color=(41, 41, 41))
            draw = ImageDraw.Draw(img)
            try:
                font = ImageFont.truetype(FONT_PATH, 48)
            except:
                font = ImageFont.load_default()
            draw.text((512, 100), "MATCHDAY", fill=(255, 255, 255), font=font, anchor="mm")
            draw.text((512, 350), "VS", fill=(255, 215, 0), font=font, anchor="mm")
            img.save(IMAGE_PATH)
            logging.info(f"✅ Standard-Matchday-Bild wurde unter '{IMAGE_PATH}' erstellt.")
        except Exception as e:
            logging.error(f"❌ Fehler beim Erstellen des Standard-Matchday-Bildes: {str(e)}")
            
    def create_default_font(self):
        try:
            with open(FONT_PATH, 'wb') as f:
                pass
            logging.warning(f"⚠️ Platzhalter für Schriftart erstellt unter '{FONT_PATH}'.")
            logging.warning(f"Bitte füge eine TrueType-Schriftart (.ttf) an diesem Speicherort hinzu.")
        except Exception as e:
            logging.error(f"❌ Fehler beim Erstellen des Schriftart-Platzhalters: {str(e)}")

    def clear_temp_files(self, user_id: int = None):
        try:
            if not os.path.exists(TEMP_PATH):
                return
            if user_id:
                for filename in os.listdir(TEMP_PATH):
                    if str(user_id) in filename:
                        file_path = os.path.join(TEMP_PATH, filename)
                        if os.path.isfile(file_path):
                            os.remove(file_path)
            else:
                for filename in os.listdir(TEMP_PATH):
                    file_path = os.path.join(TEMP_PATH, filename)
                    if os.path.isfile(file_path):
                        os.remove(file_path)
        except Exception as e:
            logging.error(f"❌ Fehler beim Löschen temporärer Dateien: {str(e)}")

    async def generate_matchday_image(self, user_id, home_logo, away_logo, home_name, away_name, post_info=None, preview=False):
        try:
            base_img = Image.open(IMAGE_PATH).convert("RGBA")
            base_img = base_img.resize((1024, 1024), Image.Resampling.LANCZOS)

            home_logo_style = self.style_manager.get_style('logo1')
            home_text_style = self.style_manager.get_style('text1')
            away_logo_style = self.style_manager.get_style('logo2')
            away_text_style = self.style_manager.get_style('text2')
            info_text_style = self.style_manager.get_style('text3')

            if home_logo:
                try:
                    home_img = Image.open(home_logo).convert("RGBA")
                    logo_size = (
                        home_logo_style.get('size', {}).get('width', 256),
                        home_logo_style.get('size', {}).get('height', 256)
                    )
                    home_img.thumbnail(logo_size, Image.Resampling.LANCZOS)
                    
                    home_pos = (
                        home_logo_style.get('position', {}).get('x', 256) - home_img.width // 2,
                        home_logo_style.get('position', {}).get('y', 300) - home_img.height // 2
                    )
                    
                    logo_layer = Image.new('RGBA', base_img.size, (0, 0, 0, 0))
                    logo_layer.paste(home_img, home_pos, home_img)
                    base_img = Image.alpha_composite(base_img, logo_layer)
                except Exception as e:
                    logging.error(f"Fehler beim Verarbeiten des Heimteam-Logos: {str(e)}")

            if away_logo:
                try:
                    away_img = Image.open(away_logo).convert("RGBA")
                    logo_size = (
                        away_logo_style.get('size', {}).get('width', 256),
                        away_logo_style.get('size', {}).get('height', 256)
                    )
                    away_img.thumbnail(logo_size, Image.Resampling.LANCZOS)
                    
                    away_pos = (
                        away_logo_style.get('position', {}).get('x', 768) - away_img.width // 2,
                        away_logo_style.get('position', {}).get('y', 300) - away_img.height // 2
                    )
                    
                    logo_layer = Image.new('RGBA', base_img.size, (0, 0, 0, 0))
                    logo_layer.paste(away_img, away_pos, away_img)
                    base_img = Image.alpha_composite(base_img, logo_layer)
                except Exception as e:
                    logging.error(f"Fehler beim Verarbeiten des Auswärtsteam-Logos: {str(e)}")

            draw = ImageDraw.Draw(base_img)

            try:
                home_font = ImageFont.truetype(FONT_PATH, home_text_style.get('size', 36))
                away_font = ImageFont.truetype(FONT_PATH, away_text_style.get('size', 36))
                info_font = ImageFont.truetype(FONT_PATH, info_text_style.get('size', 48))
            except Exception as e:
                logging.warning(f"Konnte Schriftart nicht laden: {str(e)}")
                home_font = away_font = info_font = ImageFont.load_default()

            if home_name:
                home_text_pos = (
                    home_text_style.get('position', {}).get('x', 256),
                    home_text_style.get('position', {}).get('y', 500)
                )
                draw.text(home_text_pos, home_name.upper(),
                         fill=home_text_style.get('color', "#ffffff"), 
                         font=home_font, anchor="mm")

            if away_name:
                away_text_pos = (
                    away_text_style.get('position', {}).get('x', 768),
                    away_text_style.get('position', {}).get('y', 500)
                )
                draw.text(away_text_pos, away_name.upper(),
                         fill=away_text_style.get('color', "#ffffff"), 
                         font=away_font, anchor="mm")

            if post_info and isinstance(post_info, str) and post_info.strip():
                info_text_pos = (
                    info_text_style.get('position', {}).get('x', 512),
                    info_text_style.get('position', {}).get('y', 700)
                )
                draw.text(info_text_pos, str(post_info).strip().upper(),
                         fill=info_text_style.get('color', "#ffffff"), 
                         font=info_font, anchor="mm")
                logging.info(f"Post-Info Text hinzugefügt: {post_info}")

            suffix = "_preview" if preview else "_final"
            output_path = f"{TEMP_PATH}/matchday_{user_id}{suffix}.png"
            base_img = base_img.convert('RGB')
            base_img.save(output_path, 'PNG', quality=95)

            return output_path

        except Exception as e:
            logging.error(f"❌ Fehler beim Generieren des Matchday-Bildes: {str(e)}")
            raise

    @app_commands.command(name="matchday", description="Erstellt eine Matchday-Ankündigung mit Team-Logos und -Namen")
    @app_commands.describe(action="Optionale Aktion (z.B. 'clear' zum Löschen der Zwischenspeicherdateien)")
    async def matchday_command(self, interaction: discord.Interaction, action: str = None):
        if action and action.lower() == "clear":
            self.clear_temp_files(interaction.user.id)
            embed = discord.Embed(
                title="🗑️ Zwischenspeicher geleert",
                description="Alle deine temporären Dateien wurden gelöscht.",
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
            
        if not os.path.exists(IMAGE_PATH):
            self.create_default_image()
            
        if not os.path.exists(FONT_PATH):
            self.create_default_font()
            embed = discord.Embed(
                title="⚠️ Schriftart fehlt",
                description=f"Die Schriftart wurde nicht gefunden. Bitte füge eine TrueType-Schriftart (.ttf) unter `{FONT_PATH}` hinzu.",
                color=discord.Color.orange()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
            
        embed = discord.Embed(
            title="🎮 Matchday-Ankündigung erstellen",
            description=(
                "Erstelle eine Matchday-Ankündigung mit Team-Logos und -Namen.\n\n"
                "**Anleitung:**\n"
                "1. 🏠 **Heim Team**: Logo hochladen und Namen eingeben\n"
                "2. ✈️ **Auswärts Team**: Logo hochladen und Namen eingeben\n"
                "3. 📝 **Postinfo**: Zusätzliche Informationen eingeben\n"
                "4. 👁️ **Vorschau**: Zeigt eine Vorschau deiner Ankündigung\n"
                "5. ✅ **Erstellen**: Erstellt die finale Ankündigung"
            ),
            color=discord.Color.blue()
        )
        
        view = MatchdayView(self)
        await interaction.response.send_message(embed=embed, view=view)
        original_message = await interaction.original_response()
        view.command_message = original_message
        view.start_time = original_message.created_at.replace(tzinfo=timezone.utc)

async def setup(bot):
    os.makedirs(MODULE_PATH, exist_ok=True)
    await bot.add_cog(Matchday(bot))
"""
Discord Matchday Module
Author: HuntersDesingsPaid
Version: 2.1.0
Last Updated: 2025-05-07 11:45:50 UTC
"""

import discord
from discord import app_commands
from discord.ext import commands
import os
import json
from PIL import Image, ImageDraw, ImageFont
from typing import Dict, Optional, Any
import logging
from datetime import datetime
import re
import aiofiles
import aiohttp
import asyncio
from io import BytesIO

# Konstanten
MODULE_PATH = "modules/matchday"
CACHE_PATH = f"{MODULE_PATH}/zwischenspeicher"
BASE_IMAGE_PATH = f"{MODULE_PATH}/matchday.png"
FONT_PATH = f"{MODULE_PATH}/font.ttf"
CSS_PATH = f"{MODULE_PATH}/style.css"

# Emojis für besseres UI
EMOJIS = {
    "home": "🏠",
    "away": "✈️",
    "time": "⏰",
    "create": "🎨",
    "success": "✅",
    "error": "❌",
    "warning": "⚠️",
    "wait": "⌛",
    "save": "💾",
    "upload": "📤",
    "name": "📝",
    "logo": "🖼️",
    "vs": "⚔️",
    "loading": "🔄",
    "delete": "🗑️",
    "module": "🎮",
    "settings": "⚙️",
    "help": "❓",
    "refresh": "🔁",
    "file": "📁"
}

# Default CSS wenn nicht vorhanden
DEFAULT_CSS = {
    "logo1": {"x": 200, "y": 400, "max_width": 200, "max_height": 200},
    "logo2": {"x": 824, "y": 400, "max_width": 200, "max_height": 200},
    "text1": {"x": 200, "y": 600, "size": 36, "color": "#ffffff"},
    "text2": {"x": 824, "y": 600, "size": 36, "color": "#ffffff"},
    "match_time": {"x": 512, "y": 700, "size": 48, "color": "#ffffff"}
}

class FileSelect(discord.ui.Select):
    """Dateiauswahl-Dropdown"""
    def __init__(self, files: list, team_type: str, view):
        self.team_type = team_type
        self.main_view = view
        
        options = [
            discord.SelectOption(
                label=f"Datei: {f}",
                value=f,
                emoji=EMOJIS["file"]
            ) for f in files[:25]  # Max 25 Optionen
        ]
        
        super().__init__(
            placeholder="Wähle ein Logo aus...",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        file_path = os.path.join(CACHE_PATH, self.values[0])
        
        try:
            if self.team_type == "home":
                self.main_view.home_logo = file_path
            else:
                self.main_view.away_logo = file_path
                
            await interaction.response.send_message(
                f"{EMOJIS['success']} Logo ausgewählt: {self.values[0]}",
                ephemeral=True
            )
            await self.main_view.update_status_message(interaction)
            
        except Exception as e:
            logging.error(f"Error selecting logo: {str(e)}")
            await interaction.response.send_message(
                f"{EMOJIS['error']} Fehler beim Auswählen des Logos!",
                ephemeral=True
            )

class LogoUploadView(discord.ui.View):
    """View für Logo-Upload"""
    def __init__(self, team_type: str, main_view):
        super().__init__(timeout=180)  # 3 Minuten Timeout
        self.team_type = team_type
        self.main_view = main_view
        
        # Füge vorhandene Dateien zum Dropdown hinzu
        if os.path.exists(CACHE_PATH):
            files = [f for f in os.listdir(CACHE_PATH) 
                    if f.endswith(('.png', '.jpg', '.jpeg', '.gif'))]
            if files:
                self.add_item(FileSelect(files, team_type, main_view))

    @discord.ui.button(label="Neues Logo hochladen", style=discord.ButtonStyle.primary, emoji=EMOJIS["upload"])
    async def upload_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(LogoUploadModal(self.team_type, self.main_view))

    @discord.ui.button(label="Vorschau", style=discord.ButtonStyle.secondary, emoji=EMOJIS["logo"])
    async def preview_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.team_type == "home":
            logo_path = self.main_view.home_logo
        else:
            logo_path = self.main_view.away_logo
            
        if not logo_path or not os.path.exists(logo_path):
            await interaction.response.send_message(
                f"{EMOJIS['error']} Kein Logo ausgewählt!",
                ephemeral=True
            )
            return
            
        try:
            file = discord.File(logo_path, filename="logo_preview.png")
            embed = discord.Embed(
                title=f"{EMOJIS['logo']} Logo Vorschau - {self.team_type.title()} Team",
                color=discord.Color.blue()
            )
            embed.set_image(url="attachment://logo_preview.png")
            
            await interaction.response.send_message(
                embed=embed,
                file=file,
                ephemeral=True
            )
        except Exception as e:
            logging.error(f"Error previewing logo: {str(e)}")
            await interaction.response.send_message(
                f"{EMOJIS['error']} Fehler beim Anzeigen der Vorschau!",
                ephemeral=True
            )

class LogoUploadModal(discord.ui.Modal, title="Logo Upload"):
    """Modal für Logo-Upload"""
    def __init__(self, team_type: str, view):
        super().__init__()
        self.team_type = team_type
        self.view = view
        
        self.url_input = discord.ui.TextInput(
            label="Logo URL oder Datei-Upload",
            placeholder="http://... oder wähle eine Datei aus",
            required=True,
            style=discord.TextStyle.short
        )
        self.add_item(self.url_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        url = self.url_input.value.strip()
        
        try:
            # Prüfe auf Datei-Upload
            if interaction.message and interaction.message.attachments:
                attachment = interaction.message.attachments[0]
                if not attachment.content_type or not attachment.content_type.startswith('image/'):
                    await interaction.followup.send(
                        f"{EMOJIS['error']} Die Datei ist kein Bild!",
                        ephemeral=True
                    )
                    return
                    
                # Speichere Upload
                file_ext = os.path.splitext(attachment.filename)[1]
                save_path = os.path.join(
                    CACHE_PATH,
                    f"{self.team_type}_logo_{interaction.user.id}{file_ext}"
                )
                
                await attachment.save(save_path)
                
            # Sonst versuche URL
            elif url.startswith(('http://', 'https://')):
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as response:
                        if response.status != 200:
                            await interaction.followup.send(
                                f"{EMOJIS['error']} Fehler beim Laden der URL!",
                                ephemeral=True
                            )
                            return
                            
                        data = await response.read()
                        
                        # Prüfe Dateiformat
                        try:
                            im = Image.open(BytesIO(data))
                            save_path = os.path.join(
                                CACHE_PATH,
                                f"{self.team_type}_logo_{interaction.user.id}.{im.format.lower()}"
                            )
                            im.save(save_path)
                        except:
                            await interaction.followup.send(
                                f"{EMOJIS['error']} Die URL enthält kein gültiges Bild!",
                                ephemeral=True
                            )
                            return
            else:
                await interaction.followup.send(
                    f"{EMOJIS['error']} Bitte gib eine gültige URL ein oder lade eine Datei hoch!",
                    ephemeral=True
                )
                return
                
            # Aktualisiere View
            if self.team_type == "home":
                self.view.home_logo = save_path
            else:
                self.view.away_logo = save_path
                
            await interaction.followup.send(
                f"{EMOJIS['success']} Logo erfolgreich gespeichert!",
                ephemeral=True
            )
            await self.view.update_status_message(interaction)
            
        except Exception as e:
            logging.error(f"Error processing logo: {str(e)}")
            await interaction.followup.send(
                f"{EMOJIS['error']} Fehler beim Verarbeiten des Logos!",
                ephemeral=True
            )
class TeamLogoButton(discord.ui.Button):
    """Button für Logo-Upload"""
    def __init__(self, team_type: str, disabled: bool = False):
        super().__init__(
            label=f"Logo {team_type.title()}",
            emoji=EMOJIS["logo"],
            style=discord.ButtonStyle.success if not disabled else discord.ButtonStyle.gray,
            disabled=disabled,
            custom_id=f"logo_{team_type}",
            row=1 if team_type == "home" else 2
        )
        self.team_type = team_type

    async def callback(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title=f"{EMOJIS['logo']} Logo Upload - {self.team_type.title()} Team",
            description=(
                f"**Logo hochladen:**\n\n"
                f"1. {EMOJIS['upload']} Klicke auf 'Neues Logo hochladen'\n"
                f"2. {EMOJIS['file']} Wähle dein Logo aus oder gib eine URL ein\n"
                f"3. {EMOJIS['save']} Bestätige den Upload\n\n"
                f"*Unterstützte Formate: PNG, JPG, JPEG, GIF*\n"
                f"*Max. Größe: 8 MB*"
            ),
            color=discord.Color.blue()
        )
        
        await interaction.response.send_message(
            embed=embed,
            view=LogoUploadView(self.team_type, self.view),
            ephemeral=True
        )

class TeamNameButton(discord.ui.Button):
    """Button für Team-Namen"""
    def __init__(self, team_type: str, disabled: bool = False):
        super().__init__(
            label=f"Name {team_type.title()}",
            emoji=EMOJIS["name"],
            style=discord.ButtonStyle.primary if not disabled else discord.ButtonStyle.gray,
            disabled=disabled,
            custom_id=f"name_{team_type}",
            row=1 if team_type == "home" else 2
        )
        self.team_type = team_type

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(TeamNameModal(self.team_type, self.view))

class TeamNameModal(discord.ui.Modal, title="Team Name Eingabe"):
    """Modal für Team-Namen Eingabe"""
    def __init__(self, team_type: str, view):
        super().__init__()
        self.team_type = team_type
        self.view = view
        
        self.team_name = discord.ui.TextInput(
            label=f"Name {team_type.title()} Team",
            placeholder="z.B. FC Bayern München",
            required=True,
            min_length=1,
            max_length=50
        )
        self.add_item(self.team_name)

    async def on_submit(self, interaction: discord.Interaction):
        if self.team_type == "home":
            self.view.home_name = self.team_name.value
        else:
            self.view.away_name = self.team_name.value
            
        self.view.update_button_states()
            
        await interaction.response.send_message(
            f"{EMOJIS['success']} **Team Name gespeichert!**\n"
            f"{EMOJIS['name']} {self.team_name.value}",
            ephemeral=True
        )
        await self.view.update_status_message(interaction)

class MatchTimeButton(discord.ui.Button):
    """Button für Spielzeit"""
    def __init__(self, disabled: bool = False):
        super().__init__(
            label="Spielzeit",
            emoji=EMOJIS["time"],
            style=discord.ButtonStyle.primary if not disabled else discord.ButtonStyle.gray,
            disabled=disabled,
            custom_id="match_time",
            row=3
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(TimeModal(self.view))

class TimeModal(discord.ui.Modal, title="Spielzeit Eingabe"):
    """Modal für Spielzeit Eingabe"""
    def __init__(self, view):
        super().__init__()
        self.view = view
        
        self.time_input = discord.ui.TextInput(
            label="Uhrzeit",
            placeholder="Format: HH:MM (z.B. 20:00)",
            required=True,
            min_length=5,
            max_length=5
        )
        self.add_item(self.time_input)

    async def on_submit(self, interaction: discord.Interaction):
        if not re.match(r'^([01]\d|2[0-3]):([0-5]\d)$', self.time_input.value):
            await interaction.response.send_message(
                f"{EMOJIS['error']} Ungültiges Zeitformat! Bitte nutze HH:MM (z.B. 20:00)",
                ephemeral=True
            )
            return
            
        self.view.match_time = self.time_input.value
        self.view.update_button_states()
        
        await interaction.response.send_message(
            f"{EMOJIS['success']} **Spielzeit gespeichert!**\n"
            f"{EMOJIS['time']} {self.time_input.value}",
            ephemeral=True
        )
        await self.view.update_status_message(interaction)

class CreateButton(discord.ui.Button):
    """Button für Bild-Erstellung"""
    def __init__(self):
        super().__init__(
            label="Erstellen",
            emoji=EMOJIS["create"],
            style=discord.ButtonStyle.success,
            row=4
        )

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        missing = []
        
        if not view.home_name or not view.home_logo:
            missing.extend([
                f"{EMOJIS['name']} Name Heimteam" if not view.home_name else None,
                f"{EMOJIS['logo']} Logo Heimteam" if not view.home_logo else None
            ])
            
        if not view.away_name or not view.away_logo:
            missing.extend([
                f"{EMOJIS['name']} Name Auswärtsteam" if not view.away_name else None,
                f"{EMOJIS['logo']} Logo Auswärtsteam" if not view.away_logo else None
            ])
            
        if not view.match_time:
            missing.append(f"{EMOJIS['time']} Spielzeit")
            
        missing = [m for m in missing if m is not None]
            
        if missing:
            await interaction.response.send_message(
                f"{EMOJIS['warning']} **Fehlende Angaben:**\n" + "\n".join(missing),
                ephemeral=True
            )
            return
            
        await interaction.response.defer()
        
        try:
            output_path = os.path.join(CACHE_PATH, f"matchday_{interaction.user.id}.png")
            await view.cog.generate_matchday_image(
                view.home_logo, view.away_logo,
                view.home_name, view.away_name,
                view.match_time, output_path
            )
            
            embed = discord.Embed(
                title=f"{EMOJIS['module']} Matchday Bild erstellt!",
                color=discord.Color.green(),
                timestamp=datetime.now()
            )
            embed.add_field(
                name=f"{EMOJIS['home']} Heimteam",
                value=view.home_name,
                inline=True
            )
            embed.add_field(
                name=f"{EMOJIS['away']} Auswärtsteam",
                value=view.away_name,
                inline=True
            )
            embed.add_field(
                name=f"{EMOJIS['time']} Anpfiff",
                value=view.match_time,
                inline=False
            )
            
            await interaction.followup.send(
                embed=embed,
                file=discord.File(output_path)
            )
            
            view.cleanup_files()
            try:
                os.remove(output_path)
            except Exception as e:
                logging.error(f"Error removing output file: {str(e)}")
            
            await view.message.edit(
                content=f"{EMOJIS['success']} **Bild wurde erstellt und gesendet!**",
                view=None
            )
            view.stop()
            
        except Exception as e:
            logging.error(f"Error creating matchday image: {str(e)}")
            await interaction.followup.send(
                f"{EMOJIS['error']} Fehler beim Erstellen des Bildes.",
                ephemeral=True
            )

class MatchdayView(discord.ui.View):
    """Hauptview für Matchday Erstellung"""
    def __init__(self, cog: 'MatchdayCog'):
        super().__init__(timeout=600)  # 10 Minuten Timeout
        self.cog = cog
        self.home_logo: Optional[str] = None
        self.away_logo: Optional[str] = None
        self.home_name: Optional[str] = None
        self.away_name: Optional[str] = None
        self.match_time: Optional[str] = None
        self.waiting_for_image = False
        self.current_team = None
        self.message: Optional[discord.Message] = None
        
        # Füge Buttons hinzu
        self.add_item(TeamNameButton("home"))
        self.add_item(TeamLogoButton("home"))
        self.add_item(TeamNameButton("away"))
        self.add_item(TeamLogoButton("away"))
        self.add_item(MatchTimeButton())
        self.add_item(CreateButton())

    async def on_timeout(self):
        """Timeout Handler"""
        if self.message:
            await self.message.edit(
                content=f"{EMOJIS['error']} Zeit abgelaufen! Bitte starte neu mit `/matchday`",
                view=None
            )
        self.cleanup_files()
        
    def update_button_states(self):
        """Aktualisiert den Status aller Buttons"""
        for child in self.children:
            if isinstance(child, (TeamNameButton, TeamLogoButton)):
                if child.team_type == "home":
                    child.disabled = False
                elif child.team_type == "away":
                    child.disabled = False
            elif isinstance(child, MatchTimeButton):
                child.disabled = False
            elif isinstance(child, CreateButton):
                child.disabled = not all([
                    self.home_name, self.home_logo,
                    self.away_name, self.away_logo,
                    self.match_time
                ])

    def cleanup_files(self):
        """Löscht temporäre Dateien"""
        files = [self.home_logo, self.away_logo]
        for file in files:
            if file and os.path.exists(file):
                try:
                    os.remove(file)
                except Exception as e:
                    logging.error(f"Error cleaning up file {file}: {str(e)}")

    async def update_status_message(self, interaction: discord.Interaction):
        """Aktualisiert die Statusnachricht"""
        status = [
            f"{EMOJIS['module']} **Matchday Bild erstellen**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        ]
        
        # Home team status
        status.append(f"{EMOJIS['home']} **__Heimteam:__**")
        if self.home_name:
            status.append(f"➥ {EMOJIS['name']} {self.home_name}")
        if self.home_logo:
            status.append(f"➥ {EMOJIS['success']} Logo hochgeladen")
        
        # Away team status
        status.append(f"\n{EMOJIS['away']} **__Auswärtsteam:__**")
        if self.away_name:
            status.append(f"➥ {EMOJIS['name']} {self.away_name}")
        if self.away_logo:
            status.append(f"➥ {EMOJIS['success']} Logo hochgeladen")
        
        # Match time status
        if self.match_time:
            status.append(f"\n{EMOJIS['time']} **__Spielzeit:__** {self.match_time}")
        
        status.append("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        
        # Progress info
        missing = []
        if not self.home_name or not self.home_logo:
            missing.extend([
                f"➥ {EMOJIS['name']} Name Heimteam" if not self.home_name else None,
                f"➥ {EMOJIS['logo']} Logo Heimteam" if not self.home_logo else None
            ])
        if not self.away_name or not self.away_logo:
            missing.extend([
                f"➥ {EMOJIS['name']} Name Auswärtsteam" if not self.away_name else None,
                f"➥ {EMOJIS['logo']} Logo Auswärtsteam" if not self.away_logo else None
            ])
        if not self.match_time:
            missing.append(f"➥ {EMOJIS['time']} Spielzeit")
            
        missing = [m for m in missing if m is not None]
        
        if missing:
            status.append(f"\n{EMOJIS['warning']} **Noch fehlend:**\n" + "\n".join(missing))
        else:
            status.append(
                f"\n{EMOJIS['success']} **Alle Daten komplett!**\n"
                f"➥ Klicke auf '{EMOJIS['create']} Erstellen'"
            )
        
        try:
            await self.message.edit(content="\n".join(status), view=self)
        except:
            pass

class MatchdayCog(commands.Cog):
    """Matchday Modul für Discord Bot"""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.css_data = self.load_css()
        self.active_views = {}
        self._ensure_directories()

    def _ensure_directories(self):
        """Erstellt benötigte Verzeichnisse"""
        os.makedirs(MODULE_PATH, exist_ok=True)
        os.makedirs(CACHE_PATH, exist_ok=True)

    def load_css(self) -> Dict[str, Any]:
        """Lädt CSS Konfiguration"""
        if not os.path.exists(CSS_PATH):
            with open(CSS_PATH, 'w', encoding='utf-8') as f:
                json.dump(DEFAULT_CSS, f, indent=4)
            return DEFAULT_CSS
        try:
            with open(CSS_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return DEFAULT_CSS

    async def generate_matchday_image(
        self, home_logo: str, away_logo: str,
        home_name: str, away_name: str,
        match_time: str, output_path: str
    ):
        """Generiert das Matchday Bild"""
        try:
            # Lade Basis-Bild
            base = Image.open(BASE_IMAGE_PATH).convert('RGBA')
            
            # Lade und skaliere Logos
            home = Image.open(home_logo).convert('RGBA')
            away = Image.open(away_logo).convert('RGBA')
            
            # Skaliere Logos
            home = self._resize_image(
                home,
                self.css_data['logo1']['max_width'],
                self.css_data['logo1']['max_height']
            )
            away = self._resize_image(
                away,
                self.css_data['logo2']['max_width'],
                self.css_data['logo2']['max_height']
            )
            
            # Erstelle Canvas
            canvas = Image.new('RGBA', base.size, (0, 0, 0, 0))
            
            # Berechne Positionen
            home_x = self.css_data['logo1']['x'] - home.width // 2
            home_y = self.css_data['logo1']['y'] - home.height // 2
            away_x = self.css_data['logo2']['x'] - away.width // 2
            away_y = self.css_data['logo2']['y'] - away.height // 2
            
            # Füge Logos ein
            canvas.paste(home, (home_x, home_y), home)
            canvas.paste(away, (away_x, away_y), away)
            
            # Füge Text hinzu
            draw = ImageDraw.Draw(canvas)
            
            try:
                font = ImageFont.truetype(FONT_PATH, self.css_data['text1']['size'])
            except Exception as e:
                logging.error(f"Error loading font: {str(e)}")
                font = ImageFont.load_default()
            
            def get_text_dimensions(text: str, font: ImageFont.FreeTypeFont):
                bbox = font.getbbox(text)
                return bbox[2] - bbox[0], bbox[3] - bbox[1]
            
            # Zeichne Team-Namen
            for text, x_pos, y_pos, config in [
                (home_name, self.css_data['text1']['x'],
                 self.css_data['text1']['y'], self.css_data['text1']),
                (away_name, self.css_data['text2']['x'],
                 self.css_data['text2']['y'], self.css_data['text2'])
            ]:
                w, h = get_text_dimensions(text, font)
                x = x_pos - w // 2
                draw.text((x, y_pos), text, font=font, fill=config['color'])
            
            # Zeichne Spielzeit
            time_font = font.font_variant(size=self.css_data['match_time']['size'])
            w, h = get_text_dimensions(match_time, time_font)
            time_x = self.css_data['match_time']['x'] - w // 2
            draw.text(
                (time_x, self.css_data['match_time']['y']),
                match_time,
                font=time_font,
                fill=self.css_data['match_time']['color']
            )
            
            # Kombiniere und speichere
            final = Image.alpha_composite(base, canvas)
            final.save(output_path, 'PNG')
            
        except Exception as e:
            logging.error(f"Error in image generation: {str(e)}")
            raise

    def _resize_image(self, img: Image.Image, max_width: int, max_height: int) -> Image.Image:
        """Skaliert ein Bild unter Beibehaltung des Seitenverhältnisses"""
        ratio = min(max_width/img.width, max_height/img.height)
        new_size = (int(img.width * ratio), int(img.height * ratio))
        return img.resize(new_size, Image.LANCZOS)

    @app_commands.command(name="matchday")
    @app_commands.describe(action="Optional: 'clear' zum Löschen zwischengespeicherter Bilder")
    async def matchday(self, interaction: discord.Interaction, action: Optional[str] = None):
        """Erstelle eine Matchday-Ankündigung oder lösche zwischengespeicherte Bilder"""
        if action and action.lower() == "clear":
            try:
                for file in os.listdir(CACHE_PATH):
                    file_path = os.path.join(CACHE_PATH, file)
                    if os.path.isfile(file_path):
                        os.remove(file_path)
                await interaction.response.send_message(
                    f"{EMOJIS['success']} Zwischenspeicher wurde geleert!",
                    ephemeral=True
                )
            except Exception as e:
                logging.error(f"Error clearing cache: {str(e)}")
                await interaction.response.send_message(
                    f"{EMOJIS['error']} Fehler beim Leeren des Zwischenspeichers.",
                    ephemeral=True
                )
            return

        view = MatchdayView(self)
        self.active_views[interaction.user.id] = view
        
        embed = discord.Embed(
            title=f"{EMOJIS['module']} Matchday Bild erstellen",
            description=(
                f"{EMOJIS['home']} Erstelle ein Matchday-Ankündigungsbild {EMOJIS['away']}"
            ),
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        
        embed.add_field(
            name=f"{EMOJIS['home']} Heimteam",
            value=(
                f"1️⃣ Klicke auf '{EMOJIS['name']} Name Heim'\n"
                f"2️⃣ Klicke auf '{EMOJIS['logo']} Logo Heim'"
            ),
            inline=True
        )
        
        embed.add_field(
            name=f"{EMOJIS['away']} Auswärtsteam",
            value=(
                f"3️⃣ Klicke auf '{EMOJIS['name']} Name Auswärts'\n"
                f"4️⃣ Klicke auf '{EMOJIS['logo']} Logo Auswärts'"
            ),
            inline=True
        )
        
        embed.add_field(
            name=f"{EMOJIS['time']} Spielzeit",
            value=f"5️⃣ Klicke auf '{EMOJIS['time']} Spielzeit'",
            inline=False
        )
        
        embed.add_field(
            name=f"{EMOJIS['create']} Erstellen",
            value=(
                f"6️⃣ Klicke auf '{EMOJIS['create']} Erstellen'\n"
                "*Das Bild wird automatisch generiert und gesendet.*"
            ),
            inline=False
        )
        
        embed.set_footer(
            text=f"Erstellt von {interaction.user.name}",
            icon_url=interaction.user.display_avatar.url
        )
        
        await interaction.response.send_message(
            embed=embed,
            view=view,
            ephemeral=True
        )
        
        view.message = await interaction.original_response()

async def setup(bot: commands.Bot):
    """Lädt das Matchday-Modul"""
    await bot.add_cog(MatchdayCog(bot))
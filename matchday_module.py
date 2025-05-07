import discord
import os
import asyncio
import logging
import json
import shutil
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
from datetime import datetime
from discord import app_commands
from discord.ext import commands
from discord.ui import Button, View, Modal, TextInput
from typing import Dict, List, Optional, Any, Union, Callable

# Definition der Abhängigkeiten
DEPENDENCIES = []

# Konstanten für Pfade
MODULE_PATH = "modules/matchday"
TEMP_PATH = f"{MODULE_PATH}/zwischenspeicher"
IMAGE_PATH = f"{MODULE_PATH}/matchday.png"
FONT_PATH = f"{MODULE_PATH}/font.ttf"
CSS_PATH = f"{MODULE_PATH}/styles.css"

# Klasse zum Verwalten der CSS-Styles
class StyleManager:
    """Verwaltet die CSS-Styles für die Positionierung und Formatierung von Elementen."""
    def __init__(self, css_path: str):
        self.css_path = css_path
        self.styles = self._load_styles()
        
    def _load_styles(self) -> Dict[str, Any]:
        """Lädt die Styles aus der CSS-Datei."""
        if not os.path.exists(self.css_path):
            self._create_default_styles()
            
        try:
            with open(self.css_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            logging.warning(f"⚠️ CSS-Datei konnte nicht geladen werden. Erstelle Standardstyles.")
            return self._create_default_styles()
            
    def _create_default_styles(self) -> Dict[str, Any]:
        """Erstellt Standardstyles, falls keine CSS-Datei existiert."""
        default_styles = {
            "logo1": {
                "position": {"x": 150, "y": 250},
                "size": {"width": 200, "height": 200}
            },
            "text1": {
                "position": {"x": 150, "y": 470},
                "size": 40,
                "color": "#ffffff",
                "align": "center"
            },
            "logo2": {
                "position": {"x": 650, "y": 250},
                "size": {"width": 200, "height": 200}
            },
            "text2": {
                "position": {"x": 650, "y": 470},
                "size": 40,
                "color": "#ffffff",
                "align": "center"
            },
            "text3": {
                "position": {"x": 400, "y": 600},
                "size": 30,
                "color": "#ffffff",
                "align": "center"
            }
        }
        
        # Stelle sicher, dass der Ordner existiert
        os.makedirs(os.path.dirname(self.css_path), exist_ok=True)
        
        try:
            with open(self.css_path, 'w', encoding='utf-8') as f:
                json.dump(default_styles, f, indent=4)
                logging.info(f"✅ Standardstyles wurden in '{self.css_path}' gespeichert.")
        except Exception as e:
            logging.error(f"❌ Fehler beim Erstellen der CSS-Datei: {str(e)}")
            
        return default_styles
        
    def get_style(self, element_id: str) -> Dict[str, Any]:
        """Gibt die Style-Informationen für ein bestimmtes Element zurück."""
        return self.styles.get(element_id, {})
        
    def reload(self) -> bool:
        """Lädt die Styles neu."""
        try:
            self.styles = self._load_styles()
            return True
        except Exception as e:
            logging.error(f"❌ Fehler beim Neuladen der Styles: {str(e)}")
            return False

# Klasse für das Matchday-Modal (Team-Name-Eingabe)
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
        return self.team_name.value

# Klasse für das Stream-Zeit-Modal
class StreamTimeModal(Modal):
    def __init__(self):
        super().__init__(title="Stream-Informationen eingeben")
        
        self.stream_date = TextInput(
            label="Datum (z.B. 15.05.2025)",
            placeholder="Datum des Streams",
            required=True,
            max_length=20
        )
        self.add_item(self.stream_date)
        
        self.stream_time = TextInput(
            label="Uhrzeit (z.B. 20:00 Uhr)",
            placeholder="Uhrzeit des Streams",
            required=True,
            max_length=20
        )
        self.add_item(self.stream_time)
        
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        return f"{self.stream_date.value} | {self.stream_time.value}"

# Klasse für die Matchday-View (Button-Menü)
class MatchdayView(View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog
        self.home_team_logo = None
        self.away_team_logo = None
        self.home_team_name = None
        self.away_team_name = None
        self.stream_time = None
        
        # Buttons hinzufügen
        self.add_item(Button(style=discord.ButtonStyle.primary, label="Heim Team", custom_id="home_team", emoji="🏠"))
        self.add_item(Button(style=discord.ButtonStyle.danger, label="Auswärts Team", custom_id="away_team", emoji="✈️"))
        self.add_item(Button(style=discord.ButtonStyle.success, label="Stream Zeit", custom_id="stream_time", emoji="🕒"))
        self.add_item(Button(style=discord.ButtonStyle.secondary, label="Vorschau", custom_id="preview", emoji="👁️"))
        self.add_item(Button(style=discord.ButtonStyle.primary, label="Erstellen", custom_id="create", emoji="✅"))
        
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        button_id = interaction.data["custom_id"]
        
        if button_id == "home_team":
            await self.home_team_button(interaction)
        elif button_id == "away_team":
            await self.away_team_button(interaction)
        elif button_id == "stream_time":
            await self.stream_time_button(interaction)
        elif button_id == "preview":
            await self.preview_button(interaction)
        elif button_id == "create":
            await self.create_button(interaction)
            
        return True
        
    async def home_team_button(self, interaction: discord.Interaction):
        # Namen für das Heimteam abfragen
        modal = TeamNameModal("Heim Team")
        await interaction.response.send_modal(modal)
        await modal.wait()
        
        self.home_team_name = modal.team_name.value
        
        # Aufforderung zum Upload des Logos
        embed = discord.Embed(
            title="🏠 Heim Team Logo hochladen",
            description="Bitte lade jetzt das Logo des Heimteams hoch (als Antwort auf diese Nachricht).",
            color=discord.Color.blue()
        )
        await interaction.followup.send(embed=embed)
        
        def check(m):
            return m.author.id == interaction.user.id and m.channel.id == interaction.channel.id and len(m.attachments) > 0
            
        try:
            message = await interaction.client.wait_for('message', check=check, timeout=60.0)
            
            # Logo speichern
            attachment = message.attachments[0]
            image_data = await attachment.read()
            
            # Stelle sicher, dass der Ordner existiert
            os.makedirs(TEMP_PATH, exist_ok=True)
            
            # Speichere das Bild temporär
            logo_path = f"{TEMP_PATH}/home_logo_{interaction.user.id}.png"
            with open(logo_path, 'wb') as f:
                f.write(image_data)
                
            self.home_team_logo = logo_path
            
            # Bestätigungsnachricht
            embed = discord.Embed(
                title="✅ Heim Team eingerichtet",
                description=f"**Team-Name:** {self.home_team_name}\n**Logo:** Erfolgreich hochgeladen",
                color=discord.Color.green()
            )
            await interaction.followup.send(embed=embed)
            
        except asyncio.TimeoutError:
            embed = discord.Embed(
                title="⏱️ Zeit abgelaufen",
                description="Du hast kein Logo innerhalb der Zeitbegrenzung hochgeladen.",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)
            
    async def away_team_button(self, interaction: discord.Interaction):
        # Namen für das Auswärtsteam abfragen
        modal = TeamNameModal("Auswärts Team")
        await interaction.response.send_modal(modal)
        await modal.wait()
        
        self.away_team_name = modal.team_name.value
        
        # Aufforderung zum Upload des Logos
        embed = discord.Embed(
            title="✈️ Auswärts Team Logo hochladen",
            description="Bitte lade jetzt das Logo des Auswärtsteams hoch (als Antwort auf diese Nachricht).",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=embed)
        
        def check(m):
            return m.author.id == interaction.user.id and m.channel.id == interaction.channel.id and len(m.attachments) > 0
            
        try:
            message = await interaction.client.wait_for('message', check=check, timeout=60.0)
            
            # Logo speichern
            attachment = message.attachments[0]
            image_data = await attachment.read()
            
            # Stelle sicher, dass der Ordner existiert
            os.makedirs(TEMP_PATH, exist_ok=True)
            
            # Speichere das Bild temporär
            logo_path = f"{TEMP_PATH}/away_logo_{interaction.user.id}.png"
            with open(logo_path, 'wb') as f:
                f.write(image_data)
                
            self.away_team_logo = logo_path
            
            # Bestätigungsnachricht
            embed = discord.Embed(
                title="✅ Auswärts Team eingerichtet",
                description=f"**Team-Name:** {self.away_team_name}\n**Logo:** Erfolgreich hochgeladen",
                color=discord.Color.green()
            )
            await interaction.followup.send(embed=embed)
            
        except asyncio.TimeoutError:
            embed = discord.Embed(
                title="⏱️ Zeit abgelaufen",
                description="Du hast kein Logo innerhalb der Zeitbegrenzung hochgeladen.",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)
            
    async def stream_time_button(self, interaction: discord.Interaction):
        modal = StreamTimeModal()
        await interaction.response.send_modal(modal)
        await modal.wait()
        
        self.stream_time = modal.stream_date.value + " | " + modal.stream_time.value
        
        # Bestätigungsnachricht
        embed = discord.Embed(
            title="🕒 Stream-Zeit eingerichtet",
            description=f"**Stream-Zeit:** {self.stream_time}",
            color=discord.Color.green()
        )
        await interaction.followup.send(embed=embed)
        
    async def preview_button(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        # Überprüfen, ob alle erforderlichen Daten vorhanden sind
        if not all([self.home_team_logo, self.away_team_logo, self.home_team_name, self.away_team_name]):
            embed = discord.Embed(
                title="⚠️ Unvollständige Daten",
                description="Es fehlen noch einige Informationen. Bitte fülle zuerst alle Team-Informationen aus.",
                color=discord.Color.orange()
            )
            await interaction.followup.send(embed=embed)
            return
            
        # Generiere Vorschaubild
        try:
            preview_path = await self.cog.generate_matchday_image(
                interaction.user.id,
                self.home_team_logo,
                self.away_team_logo,
                self.home_team_name,
                self.away_team_name,
                self.stream_time,
                preview=True
            )
            
            # Sende Vorschaubild
            with open(preview_path, 'rb') as f:
                file = discord.File(f, filename="matchday_preview.png")
                
            embed = discord.Embed(
                title="👁️ Vorschau deiner Matchday-Ankündigung",
                color=discord.Color.blue()
            )
            embed.set_image(url="attachment://matchday_preview.png")
            
            await interaction.followup.send(embed=embed, file=file)
            
        except Exception as e:
            embed = discord.Embed(
                title="❌ Fehler bei der Vorschau",
                description=f"Bei der Erstellung der Vorschau ist ein Fehler aufgetreten: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)
            
    async def create_button(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        # Überprüfen, ob alle erforderlichen Daten vorhanden sind
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
            await interaction.followup.send(embed=embed)
            return
            
        # Generiere finales Bild
        try:
            final_path = await self.cog.generate_matchday_image(
                interaction.user.id,
                self.home_team_logo,
                self.away_team_logo,
                self.home_team_name,
                self.away_team_name,
                self.stream_time
            )
            
            # Sende fertiges Bild
            with open(final_path, 'rb') as f:
                file = discord.File(f, filename="matchday_announcement.png")
                
            # Erstelle eine Nachricht mit dem finalen Bild
            vs_text = "🔥 **MATCHDAY** 🔥"
            if self.stream_time:
                vs_text += f"\n📆 {self.stream_time}"
                
            embed = discord.Embed(
                title=f"{self.home_team_name} vs {self.away_team_name}",
                description=vs_text,
                color=discord.Color.gold()
            )
            embed.set_image(url="attachment://matchday_announcement.png")
            embed.set_footer(text=f"Erstellt von {interaction.user.name}")
            
            await interaction.followup.send(embed=embed, file=file)
            
            # Lösche alle temporären Dateien
            self.cog.clear_temp_files(interaction.user.id)
            
        except Exception as e:
            logging.error(f"❌ Fehler beim Erstellen des Matchday-Bildes: {str(e)}")
            embed = discord.Embed(
                title="❌ Fehler beim Erstellen",
                description=f"Bei der Erstellung des Matchday-Bildes ist ein Fehler aufgetreten: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)

class Matchday(commands.Cog):
    """Modul zur Erstellung von Matchday-Ankündigungen mit Team-Logos und Informationen."""
    
    def __init__(self, bot):
        self.bot = bot
        self.style_manager = StyleManager(CSS_PATH)
        
        # Stelle sicher, dass die erforderlichen Ordner existieren
        self.create_directories()
        
    def create_directories(self):
        """Erstellt die erforderlichen Verzeichnisse."""
        os.makedirs(MODULE_PATH, exist_ok=True)
        os.makedirs(TEMP_PATH, exist_ok=True)
        
        # Überprüfe, ob das Basis-Bild vorhanden ist
        if not os.path.exists(IMAGE_PATH):
            logging.warning(f"⚠️ Matchday-Grundlagenbild nicht gefunden unter '{IMAGE_PATH}'.")
            self.create_default_image()
            
        # Überprüfe, ob die Schriftart vorhanden ist
        if not os.path.exists(FONT_PATH):
            logging.warning(f"⚠️ Schriftart nicht gefunden unter '{FONT_PATH}'.")
            self.create_default_font()
            
    def create_default_image(self):
        """Erstellt ein Standard-Matchday-Bild, falls keines vorhanden ist."""
        try:
            # Erstelle ein einfaches Bild mit schwarzem Hintergrund
            img = Image.new('RGB', (1024, 1024), color=(41, 41, 41))
            
            # Füge einen Titel hinzu
            draw = ImageDraw.Draw(img)
            try:
                font = ImageFont.truetype(FONT_PATH, 48)
            except:
                font = ImageFont.load_default()
                
            draw.text((400, 100), "MATCHDAY", fill=(255, 255, 255), font=font, anchor="mm")
            draw.text((400, 350), "VS", fill=(255, 215, 0), font=font, anchor="mm")
            
            # Speichere das Bild
            img.save(IMAGE_PATH)
            logging.info(f"✅ Standard-Matchday-Bild wurde unter '{IMAGE_PATH}' erstellt.")
        except Exception as e:
            logging.error(f"❌ Fehler beim Erstellen des Standard-Matchday-Bildes: {str(e)}")
            
    def create_default_font(self):
        """Erstellt einen Hinweis für fehlende Schriftart."""
        try:
            with open(FONT_PATH, 'wb') as f:
                # Da wir keine eingebettete Schriftart haben, erstellen wir eine leere Datei
                # und geben einen Hinweis aus
                pass
            logging.warning(f"⚠️ Platzhalter für Schriftart erstellt unter '{FONT_PATH}'.")
            logging.warning(f"Bitte füge eine TrueType-Schriftart (.ttf) an diesem Speicherort hinzu.")
        except Exception as e:
            logging.error(f"❌ Fehler beim Erstellen des Schriftart-Platzhalters: {str(e)}")
            
    def clear_temp_files(self, user_id: int = None):
        """Löscht temporäre Dateien eines bestimmten Nutzers oder alle temporären Dateien."""
        try:
            if not os.path.exists(TEMP_PATH):
                return
                
            if user_id:
                # Lösche nur Dateien eines bestimmten Nutzers
                for filename in os.listdir(TEMP_PATH):
                    if str(user_id) in filename:
                        file_path = os.path.join(TEMP_PATH, filename)
                        if os.path.isfile(file_path):
                            os.remove(file_path)
                logging.info(f"🗑️ Temporäre Dateien des Nutzers {user_id} wurden gelöscht.")
            else:
                # Lösche alle Dateien im Zwischenspeicher
                for filename in os.listdir(TEMP_PATH):
                    file_path = os.path.join(TEMP_PATH, filename)
                    if os.path.isfile(file_path):
                        os.remove(file_path)
                logging.info(f"🗑️ Alle temporären Dateien wurden gelöscht.")
        except Exception as e:
            logging.error(f"❌ Fehler beim Löschen temporärer Dateien: {str(e)}")
            
    async def generate_matchday_image(self, user_id, home_logo, away_logo, home_name, away_name, stream_time=None, preview=False):
        """Generiert das Matchday-Ankündigungsbild mit den gegebenen Daten."""
        try:
            # Lade das Basis-Bild
            base_img = Image.open(IMAGE_PATH).convert("RGBA")
            
            # Lade die Styles
            home_logo_style = self.style_manager.get_style('logo1')
            home_text_style = self.style_manager.get_style('text1')
            away_logo_style = self.style_manager.get_style('logo2')
            away_text_style = self.style_manager.get_style('text2')
            stream_text_style = self.style_manager.get_style('text3')
            
            # Füge das Heimteam-Logo hinzu
            if home_logo:
                home_img = Image.open(home_logo).convert("RGBA")
                home_img = home_img.resize((
                    home_logo_style.get('size', {}).get('width', 200),
                    home_logo_style.get('size', {}).get('height', 200)
                ))
                
                home_pos = (
                    home_logo_style.get('position', {}).get('x', 150),
                    home_logo_style.get('position', {}).get('y', 250)
                )
                
                # Füge das Logo zum Basisbild hinzu
                base_img.paste(home_img, home_pos, home_img)
                
            # Füge das Auswärtsteam-Logo hinzu
            if away_logo:
                away_img = Image.open(away_logo).convert("RGBA")
                away_img = away_img.resize((
                    away_logo_style.get('size', {}).get('width', 200),
                    away_logo_style.get('size', {}).get('height', 200)
                ))
                
                away_pos = (
                    away_logo_style.get('position', {}).get('x', 650),
                    away_logo_style.get('position', {}).get('y', 250)
                )
                
                # Füge das Logo zum Basisbild hinzu
                base_img.paste(away_img, away_pos, away_img)
                
            # Füge die Texte hinzu
            draw = ImageDraw.Draw(base_img)
            
            # Versuche, die benutzerdefinierte Schriftart zu laden
            try:
                home_font = ImageFont.truetype(FONT_PATH, home_text_style.get('size', 40))
                away_font = ImageFont.truetype(FONT_PATH, away_text_style.get('size', 40))
                stream_font = ImageFont.truetype(FONT_PATH, stream_text_style.get('size', 30))
            except:
                # Fallback auf Standard-Schriftart
                home_font = ImageFont.load_default()
                away_font = ImageFont.load_default()
                stream_font = ImageFont.load_default()
                
            # Zeichne den Heimteam-Namen
            if home_name:
                home_text_pos = (
                    home_text_style.get('position', {}).get('x', 150),
                    home_text_style.get('position', {}).get('y', 470)
                )
                home_color = home_text_style.get('color', "#ffffff")
                home_align = home_text_style.get('align', 'center')
                
                draw.text(home_text_pos, home_name, fill=home_color, font=home_font, anchor="mm" if home_align == 'center' else None)
                
            # Zeichne den Auswärtsteam-Namen
            if away_name:
                away_text_pos = (
                    away_text_style.get('position', {}).get('x', 650),
                    away_text_style.get('position', {}).get('y', 470)
                )
                away_color = away_text_style.get('color', "#ffffff")
                away_align = away_text_style.get('align', 'center')
                
                draw.text(away_text_pos, away_name, fill=away_color, font=away_font, anchor="mm" if away_align == 'center' else None)
                
            # Zeichne die Stream-Zeit, falls vorhanden
            if stream_time:
                stream_text_pos = (
                    stream_text_style.get('position', {}).get('x', 400),
                    stream_text_style.get('position', {}).get('y', 600)
                )
                stream_color = stream_text_style.get('color', "#ffffff")
                stream_align = stream_text_style.get('align', 'center')
                
                draw.text(stream_text_pos, stream_time, fill=stream_color, font=stream_font, anchor="mm" if stream_align == 'center' else None)
                
            # Speichere das Bild
            suffix = "_preview" if preview else "_final"
            output_path = f"{TEMP_PATH}/matchday_{user_id}{suffix}.png"
            base_img.save(output_path)
            
            return output_path
            
        except Exception as e:
            logging.error(f"❌ Fehler beim Generieren des Matchday-Bildes: {str(e)}")
            raise
            
    @app_commands.command(name="matchday", description="Erstellt eine Matchday-Ankündigung mit Team-Logos und -Namen")
    @app_commands.describe(action="Optionale Aktion (z.B. 'clear' zum Löschen der Zwischenspeicherdateien)")
    async def matchday_command(self, interaction: discord.Interaction, action: str = None):
        """Hauptbefehl zur Erstellung einer Matchday-Ankündigung."""
        
        # Überprüfe, ob eine spezifische Aktion ausgeführt werden soll
        if action and action.lower() == "clear":
            self.clear_temp_files(interaction.user.id)
            embed = discord.Embed(
                title="🗑️ Zwischenspeicher geleert",
                description="Alle deine temporären Dateien wurden gelöscht.",
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
            
        # Überprüfe, ob alle erforderlichen Dateien existieren
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
            
        # Starte den Matchday-Erstellungsprozess
        embed = discord.Embed(
            title="🎮 Matchday-Ankündigung erstellen",
            description=(
                "Erstelle eine Matchday-Ankündigung mit Team-Logos und -Namen.\n\n"
                "**Anleitung:**\n"
                "1. 🏠 **Heim Team**: Logo hochladen und Namen eingeben\n"
                "2. ✈️ **Auswärts Team**: Logo hochladen und Namen eingeben\n"
                "3. 🕒 **Stream Zeit**: Stream-Datum und -Uhrzeit eingeben\n"
                "4. 👁️ **Vorschau**: Zeigt eine Vorschau deiner Ankündigung\n"
                "5. ✅ **Erstellen**: Erstellt die finale Ankündigung"
            ),
            color=discord.Color.blue()
        )
        
        view = MatchdayView(self)
        await interaction.response.send_message(embed=embed, view=view)

# Setup-Funktion für das Modul
async def setup(bot):
    # Stelle sicher, dass die erforderlichen Ordner existieren
    os.makedirs(MODULE_PATH, exist_ok=True)
import discord
from discord import app_commands
from discord.ext import commands
import sqlite3
import os
import json
from typing import List, Optional, Literal, Tuple, Dict

class PaginationView(discord.ui.View):
    """📄 Pagination-View für die Anzeige von mehreren Embeds mit Navigation."""
    def __init__(self, embeds, cog, list_data, guild):
        super().__init__(timeout=None)  # Kein Timeout, damit die Buttons immer funktionieren
        self.embeds = embeds
        self.current_page = 0
        self.cog = cog
        self.list_data = list_data
        self.guild = guild
        self.message = None
        
        # 🔄 Initialisiere Button-Status
        self.update_buttons()
    
    def update_buttons(self):
        """🔄 Aktualisiert den Status der Navigationsbuttons basierend auf der aktuellen Seite."""
        # ⬅️ Deaktiviere den Zurück-Button auf der ersten Seite
        self.previous_button.disabled = self.current_page == 0
        # ➡️ Deaktiviere den Weiter-Button auf der letzten Seite
        self.next_button.disabled = self.current_page == len(self.embeds) - 1
    
    @discord.ui.button(label="◀️", style=discord.ButtonStyle.secondary)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """⬅️ Navigiert zur vorherigen Seite."""
        if self.current_page > 0:
            self.current_page -= 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)
        else:
            await interaction.response.defer()
    
    @discord.ui.button(label="▶️", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """➡️ Navigiert zur nächsten Seite."""
        if self.current_page < len(self.embeds) - 1:
            self.current_page += 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)
        else:
            await interaction.response.defer()

# 📁 Stelle sicher, dass das Datenbankverzeichnis existiert
DB_DIR = "data"
if not os.path.exists(DB_DIR):
    os.makedirs(DB_DIR)
    print(f"📁 Verzeichnis '{DB_DIR}' wurde erstellt.")

DB_PATH = os.path.join(DB_DIR, "member_lists.db")

class MemberLists(commands.Cog):
    """📋 Cog zur Verwaltung von Mitgliederlisten mit Rollen und benutzerdefinierten Anzeigenamen."""
    def __init__(self, bot):
        self.bot = bot
        self.conn = sqlite3.connect(DB_PATH)
        self.create_tables()
        print(f"🔌 MemberLists Cog wurde initialisiert und mit Datenbank verbunden.")
        
    def create_tables(self):
        """🗃️ Erstellt die notwendigen Tabellen in der Datenbank."""
        cursor = self.conn.cursor()
        
        # 📝 Tabelle für Listen
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS lists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            title TEXT NOT NULL,
            color TEXT NOT NULL,
            sorting_alphabetical INTEGER DEFAULT 0,
            message_id INTEGER,
            channel_id INTEGER,
            show_usernames INTEGER DEFAULT 0
        )
        ''')
        
        # 👥 Tabelle für Rollen in Listen mit custom_name als neues Feld
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS list_roles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            list_id INTEGER NOT NULL,
            role_id INTEGER NOT NULL,
            custom_name TEXT,
            FOREIGN KEY (list_id) REFERENCES lists(id) ON DELETE CASCADE
        )
        ''')
        
        # 🔄 Migration: Prüfe, ob die Spalte custom_name bereits existiert
        cursor.execute("PRAGMA table_info(list_roles)")
        columns = [column[1] for column in cursor.fetchall()]
        if "custom_name" not in columns:
            cursor.execute("ALTER TABLE list_roles ADD COLUMN custom_name TEXT")
            print("🔄 Migration: 'custom_name' Spalte zu list_roles hinzugefügt.")
        
        # 🔄 Migration: Prüfe, ob die Spalte show_usernames bereits existiert
        cursor.execute("PRAGMA table_info(lists)")
        columns = [column[1] for column in cursor.fetchall()]
        if "show_usernames" not in columns:
            cursor.execute("ALTER TABLE lists ADD COLUMN show_usernames INTEGER DEFAULT 0")
            print("🔄 Migration: 'show_usernames' Spalte zu lists hinzugefügt.")
        
        self.conn.commit()
    
    def cog_unload(self):
        """🔌 Wird beim Entladen des Cogs aufgerufen."""
        if self.conn:
            self.conn.close()
            print("🔌 Datenbankverbindung geschlossen.")
    
    async def get_lists_for_guild(self, guild_id: int):
        """📋 Holt alle Listen für eine bestimmte Guild."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT id, name, title, color, sorting_alphabetical, message_id, channel_id, show_usernames FROM lists WHERE guild_id = ?", (guild_id,))
        return cursor.fetchall()
    
    async def get_list_by_name(self, guild_id: int, name: str):
        """🔍 Holt eine Liste anhand ihres Namens."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT id, name, title, color, sorting_alphabetical, message_id, channel_id, show_usernames FROM lists WHERE guild_id = ? AND name = ?", (guild_id, name))
        return cursor.fetchone()
        
    async def delete_list(self, list_id: int):
        """🗑️ Löscht eine Liste und alle zugehörigen Daten."""
        cursor = self.conn.cursor()
        # 🧹 Lösche zuerst alle Rollenbeziehungen
        cursor.execute("DELETE FROM list_roles WHERE list_id = ?", (list_id,))
        # 🧹 Dann lösche die Liste selbst
        cursor.execute("DELETE FROM lists WHERE id = ?", (list_id,))
        self.conn.commit()
        return True
    
    async def get_roles_for_list(self, list_id: int):
        """👥 Holt alle Rollen-IDs und deren benutzerdefinierte Namen für eine bestimmte Liste."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT role_id, custom_name FROM list_roles WHERE list_id = ?", (list_id,))
        return cursor.fetchall()
    
    async def create_list(self, guild_id: int, name: str, title: str, color: str, sorting_alphabetical: bool = False, show_usernames: bool = False):
        """📝 Erstellt eine neue Liste."""
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO lists (guild_id, name, title, color, sorting_alphabetical, show_usernames) VALUES (?, ?, ?, ?, ?, ?)",
            (guild_id, name, title, color, 1 if sorting_alphabetical else 0, 1 if show_usernames else 0)
        )
        self.conn.commit()
        return cursor.lastrowid
    
    async def add_role_to_list(self, list_id: int, role_id: int, custom_name: Optional[str] = None):
        """➕ Fügt eine Rolle zu einer Liste hinzu mit optionalem benutzerdefinierten Namen."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT 1 FROM list_roles WHERE list_id = ? AND role_id = ?", (list_id, role_id))
        if not cursor.fetchone():  # Prüfe, ob die Rolle bereits hinzugefügt wurde
            cursor.execute("INSERT INTO list_roles (list_id, role_id, custom_name) VALUES (?, ?, ?)", 
                          (list_id, role_id, custom_name))
            self.conn.commit()
            return True
        else:
            # 🔄 Wenn die Rolle bereits existiert, aktualisiere den benutzerdefinierten Namen
            if custom_name is not None:
                cursor.execute("UPDATE list_roles SET custom_name = ? WHERE list_id = ? AND role_id = ?",
                              (custom_name, list_id, role_id))
                self.conn.commit()
            return False
    
    async def remove_role_from_list(self, list_id: int, role_id: int):
        """➖ Entfernt eine Rolle aus einer Liste."""
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM list_roles WHERE list_id = ? AND role_id = ?", (list_id, role_id))
        self.conn.commit()
        return cursor.rowcount > 0
    
    async def update_list_sorting(self, list_id: int, sorting_alphabetical: bool):
        """🔤 Aktualisiert die Sortiereinstellung einer Liste."""
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE lists SET sorting_alphabetical = ? WHERE id = ?",
            (1 if sorting_alphabetical else 0, list_id)
        )
        self.conn.commit()
        return cursor.rowcount > 0
        
    async def update_list_username_display(self, list_id: int, show_usernames: bool):
        """👤 Aktualisiert die Einstellung für die Anzeige von Benutzernamen."""
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE lists SET show_usernames = ? WHERE id = ?",
            (1 if show_usernames else 0, list_id)
        )
        self.conn.commit()
        return cursor.rowcount > 0
    
    async def update_list_message_info(self, list_id: int, message_id: int, channel_id: int):
        """💬 Aktualisiert die Message-ID und Channel-ID einer Liste."""
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE lists SET message_id = ?, channel_id = ? WHERE id = ?",
            (message_id, channel_id, list_id)
        )
        self.conn.commit()
        return cursor.rowcount > 0
    
    async def update_role_custom_name(self, list_id: int, role_id: int, custom_name: Optional[str]):
        """✏️ Aktualisiert den benutzerdefinierten Namen einer Rolle."""
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE list_roles SET custom_name = ? WHERE list_id = ? AND role_id = ?",
            (custom_name, list_id, role_id)
        )
        self.conn.commit()
        return cursor.rowcount > 0
    
    def split_long_text(self, text: str, max_length: int = 1000) -> List[str]:
        """✂️ Teilt einen langen Text in mehrere Teile auf, die jeweils max_length Zeichen lang sind."""
        if len(text) <= max_length:
            return [text]
        
        parts = []
        lines = text.split('\n')
        current_part = ""
        
        for line in lines:
            # 📏 Wenn die aktuelle Zeile zu lang ist, teile sie weiter auf
            if len(line) > max_length:
                if current_part:
                    parts.append(current_part)
                    current_part = ""
                
                # 🔪 Teile die lange Zeile in Chunks auf
                for i in range(0, len(line), max_length):
                    chunk = line[i:i + max_length]
                    if i + max_length >= len(line):
                        current_part = chunk
                    else:
                        parts.append(chunk)
            else:
                # 📊 Wenn das Hinzufügen der Zeile den Teil zu lang machen würde, beginne einen neuen Teil
                if len(current_part) + len(line) + 1 > max_length:  # +1 für den Zeilenumbruch
                    parts.append(current_part)
                    current_part = line
                else:
                    if current_part:
                        current_part += '\n' + line
                    else:
                        current_part = line
        
        # ➕ Füge den letzten Teil hinzu, falls vorhanden
        if current_part:
            parts.append(current_part)
        
        return parts
    
    async def generate_list_embeds(self, guild, list_data, page=0):
        """📊 Generiert die Embeds für eine Liste mit Paginierung."""
        list_id, name, title, color_str, sorting_alphabetical, _, _, show_usernames = list_data
        
        # 🎨 Konvertiere Farbstring in Discord-Farbe
        try:
            color = int(color_str.lstrip('#'), 16)
        except ValueError:
            color = 0x5865F2  # Standard Discord-Blau als Fallback
        
        role_entries = await self.get_roles_for_list(list_id)
        if not role_entries:
            embed = discord.Embed(title=title, color=color)
            embed.description = "📭 Keine Rollen in dieser Liste."
            return [embed], 0  # Nur ein Embed, keine Paginierung nötig
        
        role_data = []
        for role_id, custom_name in role_entries:
            role = guild.get_role(role_id)
            if role:
                display_name = custom_name if custom_name else role.name
                role_data.append((role, display_name))
        
        if not role_data:
            embed = discord.Embed(title=title, color=color)
            embed.description = "⚠️ Keine gültigen Rollen in dieser Liste."
            return [embed], 0  # Nur ein Embed, keine Paginierung nötig
        
        if sorting_alphabetical:
            # 🔤 Sortiere nach dem Anzeigenamen, nicht nach dem tatsächlichen Rollennamen
            role_data.sort(key=lambda x: x[1].lower())
        
        # 📝 Vorbereiten der Daten für alle Embeds
        all_embeds = []
        current_embed = discord.Embed(title=title, color=color)
        current_fields = 0
        MAX_FIELDS = 25  # Discord-Limit für Felder pro Embed
        
        # Trennlinie für bessere Übersicht zwischen Segmenten (kompakter)
        separator = "\n▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬"
        
        for role, display_name in role_data:
            members = role.members
            if sorting_alphabetical:
                members = sorted(members, key=lambda x: x.display_name.lower())
            
            if not members:
                # Wenn keine Mitglieder vorhanden sind, füge ein einfaches Feld hinzu
                if current_fields >= MAX_FIELDS:
                    all_embeds.append(current_embed)
                    current_embed = discord.Embed(title=title, color=color)
                    current_fields = 0
                
                # Füge den Separator direkt am Ende des Feldinhalts hinzu
                current_embed.add_field(name=display_name, value=f"Keine Mitglieder{separator}", inline=False)
                current_fields += 1
                continue
            
            # Formatiere die Mitgliederliste je nach Einstellung
            member_lines = []
            for member in members:
                # Stelle sicher, dass immer die Mention verwendet wird
                if show_usernames:
                    # Format: @user | Username
                    member_lines.append(f"• {member.mention} | {member.display_name}")
                else:
                    # Nur Mention
                    member_lines.append(f"• {member.mention}")
            
            # Erstelle die Mitgliederliste ohne zusätzliche Leerzeilen
            member_list = "\n".join(member_lines)
            
            # Prüfe, ob die Mitgliederliste zu lang ist (Discord-Limit: 1024 Zeichen pro Feld)
            if len(member_list) <= 1024:
                # Wenn die Liste in ein Feld passt
                if current_fields >= MAX_FIELDS:
                    all_embeds.append(current_embed)
                    current_embed = discord.Embed(title=title, color=color)
                    current_fields = 0
                
                # Füge den Separator direkt am Ende des Feldinhalts hinzu
                current_embed.add_field(name=display_name, value=f"{member_list}{separator}", inline=False)
                current_fields += 1
            else:
                # Wenn die Liste zu lang ist, teile sie auf mehrere Felder auf
                parts = self.split_long_text(member_list, 1000)  # Etwas Puffer lassen
                
                for i, part in enumerate(parts):
                    if current_fields >= MAX_FIELDS:
                        all_embeds.append(current_embed)
                        current_embed = discord.Embed(title=title, color=color)
                        current_fields = 0
                    
                    field_name = f"{display_name}" if i == 0 else f"{display_name} (Fortsetzung {i+1})"
                    
                    # Füge den Separator nur am Ende des letzten Teils hinzu
                    if i == len(parts) - 1:
                        current_embed.add_field(name=field_name, value=f"{part}{separator}", inline=False)
                    else:
                        current_embed.add_field(name=field_name, value=part, inline=False)
                    
                    current_fields += 1
        
        # Füge das letzte Embed hinzu, falls es Felder enthält
        if current_fields > 0:
            all_embeds.append(current_embed)
        
        # Füge Seitenzahlen hinzu, wenn es mehr als ein Embed gibt
        if len(all_embeds) > 1:
            for i, embed in enumerate(all_embeds):
                embed.set_footer(text=f"Seite {i+1}/{len(all_embeds)}")
        
        # Stelle sicher, dass die Seitenzahl gültig ist
        page = max(0, min(page, len(all_embeds) - 1)) if all_embeds else 0
        
        return all_embeds, page
    
    async def generate_list_embed(self, guild, list_data):
        """📄 Generiert das Embed für eine Liste (Kompatibilitätsfunktion)."""
        embeds, _ = await self.generate_list_embeds(guild, list_data)
        return embeds[0] if embeds else discord.Embed(title="❌ Fehler", description="Keine Daten verfügbar.")
    
    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        """👤 Wird aufgerufen, wenn sich ein Mitglied aktualisiert (z.B. Rollen ändern)."""
        if before.roles != after.roles:
            # 🔄 Wenn sich die Rollen geändert haben, müssen wir potenziell Listen aktualisieren
            lists = await self.get_lists_for_guild(after.guild.id)
            for list_data in lists:
                list_id = list_data[0]
                message_id = list_data[5]
                channel_id = list_data[6]
                
                if message_id and channel_id:
                    role_entries = await self.get_roles_for_list(list_id)
                    role_ids = [entry[0] for entry in role_entries]
                    # 🔍 Prüfe, ob eine der geänderten Rollen in unserer Liste ist
                    if any(role.id in role_ids for role in set(before.roles + after.roles)):
                        channel = after.guild.get_channel(channel_id)
                        if channel:
                            try:
                                message = await channel.fetch_message(message_id)
                                
                                # 🔍 Prüfe, ob die Nachricht bereits eine View hat (Paginierung)
                                if message.components:  # Hat Buttons
                                    embeds, _ = await self.generate_list_embeds(after.guild, list_data)
                                    
                                    # 🔄 Erstelle eine neue View mit den aktualisierten Embeds
                                    view = PaginationView(embeds, self, list_data, after.guild)
                                    view.message = message
                                    
                                    # 📌 Behalte die aktuelle Seite bei
                                    current_page = 0
                                    if message.embeds and message.embeds[0].footer:
                                        footer_text = message.embeds[0].footer.text
                                        if footer_text and "Seite " in footer_text:
                                            try:
                                                page_info = footer_text.split("Seite ")[1]
                                                current_page = int(page_info.split("/")[0]) - 1
                                                current_page = max(0, min(current_page, len(embeds) - 1))
                                                view.current_page = current_page
                                                view.update_buttons()
                                            except (IndexError, ValueError):
                                                pass
                                    
                                    await message.edit(embed=embeds[current_page], view=view)
                                else:
                                    # 📄 Einfaches Embed ohne Paginierung
                                    embed = await self.generate_list_embed(after.guild, list_data)
                                    await message.edit(embed=embed)
                            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                                pass  # Ignoriere Fehler, wenn die Nachricht nicht mehr existiert oder nicht bearbeitet werden kann
    
    # 🔍 Autocomplete-Funktion für Listen-Namen
    async def list_name_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        guild_id = interaction.guild.id
        lists = await self.get_lists_for_guild(guild_id)
        
        list_names = [list_data[1] for list_data in lists]
        filtered_names = [name for name in list_names if current.lower() in name.lower()]
        
        return [app_commands.Choice(name=name, value=name) for name in filtered_names[:25]]
    
    # --- 📋 Commands ---
    
    @app_commands.command(name="liste_create", description="Erstellt eine neue Mitgliederliste")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(
        name="Name der Liste für die Speicherung",
        title="Überschrift der Liste, die angezeigt wird",
        color="Farbe des Embeds (Hex-Code, z.B. #FF0000 für Rot)"
    )
    async def liste_create(self, interaction: discord.Interaction, name: str, title: str, color: str):
        # 🎨 Validiere Farbe
        if not color.startswith('#'):
            color = f"#{color}"
        
        try:
            int(color.lstrip('#'), 16)
        except ValueError:
            await interaction.response.send_message("❌ Ungültiger Farbcode. Bitte gib einen gültigen Hex-Code ein (z.B. #FF0000).", ephemeral=True)
            return
        
        # 🔍 Prüfe, ob bereits eine Liste mit diesem Namen existiert
        existing_list = await self.get_list_by_name(interaction.guild.id, name)
        if existing_list:
            await interaction.response.send_message(f"⚠️ Eine Liste mit dem Namen '{name}' existiert bereits.", ephemeral=True)
            return
        
        # 📝 Erstelle neue Liste
        await self.create_list(interaction.guild.id, name, title, color)
        await interaction.response.send_message(f"✅ Liste '{name}' wurde erfolgreich erstellt.", ephemeral=True)
    
    @app_commands.command(name="liste_addrole", description="Fügt eine Rolle zu einer Liste hinzu")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.autocomplete(list_name=list_name_autocomplete)
    @app_commands.describe(
        list_name="Name der Liste",
        role="Rolle, die hinzugefügt werden soll",
        role_name="Benutzerdefinierter Anzeigename für die Rolle (optional)"
    )
    async def liste_addrole(self, interaction: discord.Interaction, list_name: str, role: discord.Role, role_name: Optional[str] = None):
        list_data = await self.get_list_by_name(interaction.guild.id, list_name)
        if not list_data:
            await interaction.response.send_message(f"❓ Liste '{list_name}' nicht gefunden.", ephemeral=True)
            return
        
        list_id = list_data[0]
        is_new = await self.add_role_to_list(list_id, role.id, role_name)
        
        display_name = role_name if role_name else role.name
        
        if is_new:
            await interaction.response.send_message(f"✅ Rolle '{role.name}' wurde zur Liste '{list_name}' hinzugefügt{f' mit dem Anzeigenamen \'{display_name}\'' if role_name else ''}.", ephemeral=True)
        else:
            # Wenn die Rolle bereits existiert und ein neuer Name angegeben wurde
            if role_name is not None:
                await self.update_role_custom_name(list_id, role.id, role_name)
                await interaction.response.send_message(f"✏️ Der Anzeigename der Rolle '{role.name}' wurde auf '{display_name}' aktualisiert.", ephemeral=True)
            else:
                await interaction.response.send_message(f"ℹ️ Rolle '{role.name}' ist bereits in der Liste '{list_name}'.", ephemeral=True)
        
        # Aktualisiere die Nachricht, falls vorhanden
        message_id = list_data[5]
        channel_id = list_data[6]
        if message_id and channel_id:
            channel = interaction.guild.get_channel(channel_id)
            if channel:
                try:
                    message = await channel.fetch_message(message_id)
                    
                    # Prüfe, ob die Nachricht bereits eine View hat (Paginierung)
                    if message.components:  # Hat Buttons
                        embeds, _ = await self.generate_list_embeds(interaction.guild, list_data)
                        
                        # Erstelle eine neue View mit den aktualisierten Embeds
                        view = PaginationView(embeds, self, list_data, interaction.guild)
                        view.message = message
                        
                        # Behalte die aktuelle Seite bei
                        current_page = 0
                        if message.embeds and message.embeds[0].footer:
                            footer_text = message.embeds[0].footer.text
                            if footer_text and "Seite " in footer_text:
                                try:
                                    page_info = footer_text.split("Seite ")[1]
                                    current_page = int(page_info.split("/")[0]) - 1
                                    current_page = max(0, min(current_page, len(embeds) - 1))
                                    view.current_page = current_page
                                    view.update_buttons()
                                except (IndexError, ValueError):
                                    pass
                        
                        await message.edit(embed=embeds[current_page], view=view)
                    else:
                        # Einfaches Embed ohne Paginierung
                        embed = await self.generate_list_embed(interaction.guild, list_data)
                        await message.edit(embed=embed)
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    pass  # Ignoriere Fehler, wenn die Nachricht nicht mehr existiert
    
    @app_commands.command(name="liste_deleterole", description="Entfernt eine Rolle aus einer Liste")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.autocomplete(list_name=list_name_autocomplete)
    @app_commands.describe(
        list_name="Name der Liste",
        role="Rolle, die entfernt werden soll"
    )
    async def liste_deleterole(self, interaction: discord.Interaction, list_name: str, role: discord.Role):
        list_data = await self.get_list_by_name(interaction.guild.id, list_name)
        if not list_data:
            await interaction.response.send_message(f"Liste '{list_name}' nicht gefunden.", ephemeral=True)
            return
        
        list_id = list_data[0]
        success = await self.remove_role_from_list(list_id, role.id)
        
        if success:
            await interaction.response.send_message(f"Rolle '{role.name}' wurde aus der Liste '{list_name}' entfernt.", ephemeral=True)
            
            # Aktualisiere die Nachricht, falls vorhanden
            message_id = list_data[5]
            channel_id = list_data[6]
            if message_id and channel_id:
                channel = interaction.guild.get_channel(channel_id)
                if channel:
                    try:
                        message = await channel.fetch_message(message_id)
                        
                        # Prüfe, ob die Nachricht bereits eine View hat (Paginierung)
                        if message.components:  # Hat Buttons
                            embeds, _ = await self.generate_list_embeds(interaction.guild, list_data)
                            
                            # Erstelle eine neue View mit den aktualisierten Embeds
                            view = PaginationView(embeds, self, list_data, interaction.guild)
                            view.message = message
                            
                            # Behalte die aktuelle Seite bei
                            current_page = 0
                            if message.embeds and message.embeds[0].footer:
                                footer_text = message.embeds[0].footer.text
                                if footer_text and "Seite " in footer_text:
                                    try:
                                        page_info = footer_text.split("Seite ")[1]
                                        current_page = int(page_info.split("/")[0]) - 1
                                        current_page = max(0, min(current_page, len(embeds) - 1))
                                        view.current_page = current_page
                                        view.update_buttons()
                                    except (IndexError, ValueError):
                                        pass
                            
                            await message.edit(embed=embeds[current_page], view=view)
                        else:
                            # Einfaches Embed ohne Paginierung
                            embed = await self.generate_list_embed(interaction.guild, list_data)
                            await message.edit(embed=embed)
                    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                        pass
        else:
            await interaction.response.send_message(f"Rolle '{role.name}' ist nicht in der Liste '{list_name}'.", ephemeral=True)
    
    @app_commands.command(name="liste_edit", description="Bearbeitet eine bestehende Liste")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.autocomplete(list_name=list_name_autocomplete)
    @app_commands.describe(
        list_name="Name der zu bearbeitenden Liste",
        new_title="Neue Überschrift für die Liste (optional)",
        new_color="Neue Farbe für das Embed (Hex-Code, z.B. #FF0000) (optional)"
    )
    async def liste_edit(self, interaction: discord.Interaction, list_name: str, new_title: Optional[str] = None, new_color: Optional[str] = None):
        list_data = await self.get_list_by_name(interaction.guild.id, list_name)
        if not list_data:
            await interaction.response.send_message(f"Liste '{list_name}' nicht gefunden.", ephemeral=True)
            return
        
        list_id = list_data[0]
        
        # Aktualisiere die Liste in der Datenbank
        cursor = self.conn.cursor()
        update_fields = []
        params = []
        
        if new_title:
            update_fields.append("title = ?")
            params.append(new_title)
        
        if new_color:
            if not new_color.startswith('#'):
                new_color = f"#{new_color}"
            
            try:
                int(new_color.lstrip('#'), 16)
                update_fields.append("color = ?")
                params.append(new_color)
            except ValueError:
                await interaction.response.send_message("Ungültiger Farbcode. Bitte gib einen gültigen Hex-Code ein (z.B. #FF0000).", ephemeral=True)
                return
        
        if not update_fields:
            await interaction.response.send_message("Keine Änderungen angegeben.", ephemeral=True)
            return
        
        params.append(list_id)
        cursor.execute(f"UPDATE lists SET {', '.join(update_fields)} WHERE id = ?", params)
        self.conn.commit()
        
        await interaction.response.send_message(f"Liste '{list_name}' wurde aktualisiert.", ephemeral=True)
        
        # Aktualisiere die Nachricht, falls vorhanden
        message_id = list_data[5]
        channel_id = list_data[6]
        if message_id and channel_id:
            channel = interaction.guild.get_channel(channel_id)
            if channel:
                try:
                    message = await channel.fetch_message(message_id)
                    # Hole die aktualisierten Listendaten
                    updated_list_data = await self.get_list_by_name(interaction.guild.id, list_name)
                    
                    # Prüfe, ob die Nachricht bereits eine View hat (Paginierung)
                    if message.components:  # Hat Buttons
                        embeds, _ = await self.generate_list_embeds(interaction.guild, updated_list_data)
                        
                        # Erstelle eine neue View mit den aktualisierten Embeds
                        view = PaginationView(embeds, self, updated_list_data, interaction.guild)
                        view.message = message
                        
                        # Behalte die aktuelle Seite bei
                        current_page = 0
                        if message.embeds and message.embeds[0].footer:
                            footer_text = message.embeds[0].footer.text
                            if footer_text and "Seite " in footer_text:
                                try:
                                    page_info = footer_text.split("Seite ")[1]
                                    current_page = int(page_info.split("/")[0]) - 1
                                    current_page = max(0, min(current_page, len(embeds) - 1))
                                    view.current_page = current_page
                                    view.update_buttons()
                                except (IndexError, ValueError):
                                    pass
                        
                        await message.edit(embed=embeds[current_page], view=view)
                    else:
                        # Einfaches Embed ohne Paginierung
                        embed = await self.generate_list_embed(interaction.guild, updated_list_data)
                        await message.edit(embed=embed)
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    pass
    
    @app_commands.command(name="liste_rename_role", description="Ändert den Anzeigenamen einer Rolle in einer Liste")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.autocomplete(list_name=list_name_autocomplete)
    @app_commands.describe(
        list_name="Name der Liste",
        role="Rolle, deren Anzeigename geändert werden soll",
        new_name="Neuer Anzeigename für die Rolle (leer lassen, um den ursprünglichen Namen wiederherzustellen)"
    )
    async def liste_rename_role(self, interaction: discord.Interaction, list_name: str, role: discord.Role, new_name: Optional[str] = None):
        list_data = await self.get_list_by_name(interaction.guild.id, list_name)
        if not list_data:
            await interaction.response.send_message(f"Liste '{list_name}' nicht gefunden.", ephemeral=True)
            return
        
        list_id = list_data[0]
        
        # Prüfe, ob die Rolle in der Liste ist
        cursor = self.conn.cursor()
        cursor.execute("SELECT 1 FROM list_roles WHERE list_id = ? AND role_id = ?", (list_id, role.id))
        if not cursor.fetchone():
            await interaction.response.send_message(f"Rolle '{role.name}' ist nicht in der Liste '{list_name}'.", ephemeral=True)
            return
        
        # Aktualisiere den benutzerdefinierten Namen
        await self.update_role_custom_name(list_id, role.id, new_name)
        
        if new_name:
            await interaction.response.send_message(f"Der Anzeigename der Rolle '{role.name}' wurde auf '{new_name}' aktualisiert.", ephemeral=True)
        else:
            await interaction.response.send_message(f"Der Anzeigename der Rolle '{role.name}' wurde auf den Standardnamen zurückgesetzt.", ephemeral=True)
        
        # Aktualisiere die Nachricht, falls vorhanden
        message_id = list_data[5]
        channel_id = list_data[6]
        if message_id and channel_id:
            channel = interaction.guild.get_channel(channel_id)
            if channel:
                try:
                    message = await channel.fetch_message(message_id)
                    
                    # Prüfe, ob die Nachricht bereits eine View hat (Paginierung)
                    if message.components:  # Hat Buttons
                        embeds, _ = await self.generate_list_embeds(interaction.guild, list_data)
                        
                        # Erstelle eine neue View mit den aktualisierten Embeds
                        view = PaginationView(embeds, self, list_data, interaction.guild)
                        view.message = message
                        
                        # Behalte die aktuelle Seite bei
                        current_page = 0
                        if message.embeds and message.embeds[0].footer:
                            footer_text = message.embeds[0].footer.text
                            if footer_text and "Seite " in footer_text:
                                try:
                                    page_info = footer_text.split("Seite ")[1]
                                    current_page = int(page_info.split("/")[0]) - 1
                                    current_page = max(0, min(current_page, len(embeds) - 1))
                                    view.current_page = current_page
                                    view.update_buttons()
                                except (IndexError, ValueError):
                                    pass
                        
                        await message.edit(embed=embeds[current_page], view=view)
                    else:
                        # Einfaches Embed ohne Paginierung
                        embed = await self.generate_list_embed(interaction.guild, list_data)
                        await message.edit(embed=embed)
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    pass
    
    @app_commands.command(name="liste_overview", description="Zeigt eine Übersicht aller Listen an")
    @app_commands.checks.has_permissions(administrator=True)
    async def liste_overview(self, interaction: discord.Interaction):
        lists = await self.get_lists_for_guild(interaction.guild.id)
        
        if not lists:
            await interaction.response.send_message("Es sind keine Listen vorhanden.", ephemeral=True)
            return
        
        embed = discord.Embed(
            title="Listenübersicht",
            color=0x5865F2,
            description=f"Insgesamt {len(lists)} Listen"
        )
        
        for list_data in lists:
            list_id, name, title, color, sorting, message_id, channel_id, show_usernames = list_data
            role_entries = await self.get_roles_for_list(list_id)
            
            role_info = []
            for role_id, custom_name in role_entries:
                role = interaction.guild.get_role(role_id)
                if role:
                    display_name = custom_name if custom_name else role.name
                    # Zeige den benutzerdefinierten Namen und den tatsächlichen Rollennamen an, wenn sie unterschiedlich sind
                    if custom_name:
                        role_info.append(f"{display_name} ({role.name})")
                    else:
                        role_info.append(role.name)
            
            embed.add_field(
                name=name,
                value=(
                    f"**Titel:** {title}\n"
                    f"**Farbe:** {color}\n"
                    f"**Sortierung:** {'Alphabetisch' if sorting else 'Standard'}\n"
                    f"**Format:** {'@user | Username' if show_usernames else 'Nur @user'}\n"
                    f"**Rollen:** {', '.join(role_info) if role_info else 'Keine'}\n"
                    f"**Nachricht aktiv:** {'Ja' if message_id else 'Nein'}"
                ),
                inline=False
            )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @app_commands.command(name="liste_update", description="Aktualisiert alle Listen des Servers")
    @app_commands.checks.has_permissions(administrator=True)
    async def liste_update(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        lists = await self.get_lists_for_guild(interaction.guild.id)
        updated_count = 0
        
        for list_data in lists:
            message_id = list_data[5]
            channel_id = list_data[6]
            
            if message_id and channel_id:
                channel = interaction.guild.get_channel(channel_id)
                if channel:
                    try:
                        message = await channel.fetch_message(message_id)
                        
                        # Prüfe, ob die Nachricht bereits eine View hat (Paginierung)
                        if message.components:  # Hat Buttons
                            embeds, _ = await self.generate_list_embeds(interaction.guild, list_data)
                            
                            # Erstelle eine neue View mit den aktualisierten Embeds
                            view = PaginationView(embeds, self, list_data, interaction.guild)
                            view.message = message
                            
                            # Behalte die aktuelle Seite bei
                            current_page = 0
                            if message.embeds and message.embeds[0].footer:
                                footer_text = message.embeds[0].footer.text
                                if footer_text and "Seite " in footer_text:
                                    try:
                                        page_info = footer_text.split("Seite ")[1]
                                        current_page = int(page_info.split("/")[0]) - 1
                                        current_page = max(0, min(current_page, len(embeds) - 1))
                                        view.current_page = current_page
                                        view.update_buttons()
                                    except (IndexError, ValueError):
                                        pass
                            
                            await message.edit(embed=embeds[current_page], view=view)
                        else:
                            # Einfaches Embed ohne Paginierung
                            embed = await self.generate_list_embed(interaction.guild, list_data)
                            await message.edit(embed=embed)
                            
                        updated_count += 1
                    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                        pass
        
        await interaction.followup.send(f"{updated_count} von {len(lists)} Listen wurden aktualisiert.", ephemeral=True)
    
    @app_commands.command(name="liste_send", description="Sendet eine Liste in den aktuellen Kanal")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.autocomplete(list_name=list_name_autocomplete)
    @app_commands.describe(list_name="Name der Liste, die gesendet werden soll")
    async def liste_send(self, interaction: discord.Interaction, list_name: str):
        list_data = await self.get_list_by_name(interaction.guild.id, list_name)
        if not list_data:
            await interaction.response.send_message(f"Liste '{list_name}' nicht gefunden.", ephemeral=True)
            return
        
        embeds, current_page = await self.generate_list_embeds(interaction.guild, list_data)
        
        await interaction.response.send_message("Liste wird gesendet...", ephemeral=True)
        
        # Wenn es nur ein Embed gibt, sende es einfach
        if len(embeds) == 1:
            message = await interaction.channel.send(embed=embeds[0])
            # Speichere die Nachrichten-ID und Kanal-ID
            await self.update_list_message_info(list_data[0], message.id, interaction.channel.id)
            return
        
        # Wenn es mehrere Embeds gibt, füge Navigationstasten hinzu
        view = PaginationView(embeds, self, list_data, interaction.guild)
        message = await interaction.channel.send(embed=embeds[0], view=view)
        view.message = message
        
        # Speichere die Nachrichten-ID und Kanal-ID
        await self.update_list_message_info(list_data[0], message.id, interaction.channel.id)
    
    @app_commands.command(name="liste_format", description="Ändert das Anzeigeformat der Mitglieder in einer Liste")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.autocomplete(list_name=list_name_autocomplete)
    @app_commands.describe(
        list_name="Name der Liste",
        show_usernames="Ob zusätzlich zu den Mentions auch die Benutzernamen angezeigt werden sollen"
    )
    async def liste_format(self, interaction: discord.Interaction, list_name: str, show_usernames: Literal['Ja', 'Nein']):
        list_data = await self.get_list_by_name(interaction.guild.id, list_name)
        if not list_data:
            await interaction.response.send_message(f"Liste '{list_name}' nicht gefunden.", ephemeral=True)
            return
        
        list_id = list_data[0]
        show_usernames_bool = show_usernames == "Ja"
        
        await self.update_list_username_display(list_id, show_usernames_bool)
        await interaction.response.send_message(
            f"Format für Liste '{list_name}' wurde auf {'@user | Username' if show_usernames_bool else 'Nur @user'} gesetzt.",
            ephemeral=True
        )
        
        # Aktualisiere die Nachricht, falls vorhanden
        message_id = list_data[5]
        channel_id = list_data[6]
        if message_id and channel_id:
            channel = interaction.guild.get_channel(channel_id)
            if channel:
                try:
                    message = await channel.fetch_message(message_id)
                    # Hole die aktualisierten Listendaten
                    updated_list_data = await self.get_list_by_name(interaction.guild.id, list_name)
                    
                    # Prüfe, ob die Nachricht bereits eine View hat (Paginierung)
                    if message.components:  # Hat Buttons
                        embeds, _ = await self.generate_list_embeds(interaction.guild, updated_list_data)
                        
                        # Erstelle eine neue View mit den aktualisierten Embeds
                        view = PaginationView(embeds, self, updated_list_data, interaction.guild)
                        view.message = message
                        
                        # Behalte die aktuelle Seite bei
                        current_page = 0
                        if message.embeds and message.embeds[0].footer:
                            footer_text = message.embeds[0].footer.text
                            if footer_text and "Seite " in footer_text:
                                try:
                                    page_info = footer_text.split("Seite ")[1]
                                    current_page = int(page_info.split("/")[0]) - 1
                                    current_page = max(0, min(current_page, len(embeds) - 1))
                                    view.current_page = current_page
                                    view.update_buttons()
                                except (IndexError, ValueError):
                                    pass
                        
                        await message.edit(embed=embeds[current_page], view=view)
                    else:
                        # Einfaches Embed ohne Paginierung
                        embed = await self.generate_list_embed(interaction.guild, updated_list_data)
                        await message.edit(embed=embed)
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    pass
    
    @app_commands.command(name="liste_sorting", description="Ändert die Sortiereinstellung einer Liste")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.autocomplete(list_name=list_name_autocomplete)
    @app_commands.describe(
        list_name="Name der Liste",
        alphabetical="Ob die Liste alphabetisch sortiert werden soll"
    )
    async def liste_sorting(self, interaction: discord.Interaction, list_name: str, alphabetical: Literal['Ja', 'Nein']):
        list_data = await self.get_list_by_name(interaction.guild.id, list_name)
        if not list_data:
            await interaction.response.send_message(f"Liste '{list_name}' nicht gefunden.", ephemeral=True)
            return
        
        list_id = list_data[0]
        sorting_alphabetical = alphabetical == "Ja"
        
        await self.update_list_sorting(list_id, sorting_alphabetical)
        await interaction.response.send_message(
            f"Sortierung für Liste '{list_name}' wurde auf {'alphabetisch' if sorting_alphabetical else 'Standard'} gesetzt.",
            ephemeral=True
        )
        
        # Aktualisiere die Nachricht, falls vorhanden
        message_id = list_data[5]
        channel_id = list_data[6]
        if message_id and channel_id:
            channel = interaction.guild.get_channel(channel_id)
            if channel:
                try:
                    message = await channel.fetch_message(message_id)
                    # Hole die aktualisierten Listendaten
                    updated_list_data = await self.get_list_by_name(interaction.guild.id, list_name)
                    
                    # Prüfe, ob die Nachricht bereits eine View hat (Paginierung)
                    if message.components:  # Hat Buttons
                        embeds, _ = await self.generate_list_embeds(interaction.guild, updated_list_data)
                        
                        # Erstelle eine neue View mit den aktualisierten Embeds
                        view = PaginationView(embeds, self, updated_list_data, interaction.guild)
                        view.message = message
                        
                        # Behalte die aktuelle Seite bei
                        current_page = 0
                        if message.embeds and message.embeds[0].footer:
                            footer_text = message.embeds[0].footer.text
                            if footer_text and "Seite " in footer_text:
                                try:
                                    page_info = footer_text.split("Seite ")[1]
                                    current_page = int(page_info.split("/")[0]) - 1
                                    current_page = max(0, min(current_page, len(embeds) - 1))
                                    view.current_page = current_page
                                    view.update_buttons()
                                except (IndexError, ValueError):
                                    pass
                        
                        await message.edit(embed=embeds[current_page], view=view)
                    else:
                        # Einfaches Embed ohne Paginierung
                        embed = await self.generate_list_embed(interaction.guild, updated_list_data)
                        await message.edit(embed=embed)
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    pass
    
    @app_commands.command(name="liste_delete", description="Löscht eine bestehende Liste")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.autocomplete(list_name=list_name_autocomplete)
    @app_commands.describe(list_name="Name der Liste, die gelöscht werden soll")
    async def liste_delete(self, interaction: discord.Interaction, list_name: str):
        list_data = await self.get_list_by_name(interaction.guild.id, list_name)
        if not list_data:
            await interaction.response.send_message(f"❓ Liste '{list_name}' nicht gefunden.", ephemeral=True)
            return
        
        list_id, name, title, color, sorting, message_id, channel_id, _ = list_data
        
        # 🗑️ Versuche, die Nachricht zu löschen, falls vorhanden
        if message_id and channel_id:
            channel = interaction.guild.get_channel(channel_id)
            if channel:
                try:
                    message = await channel.fetch_message(message_id)
                    await message.delete()
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    pass  # Ignoriere Fehler, wenn die Nachricht nicht mehr existiert
        
        # 🗑️ Lösche die Liste aus der Datenbank
        await self.delete_list(list_id)
        
        await interaction.response.send_message(f"✅ Liste '{list_name}' wurde erfolgreich gelöscht.", ephemeral=True)


async def setup(bot):
    """🚀 Initialisiert das MemberLists-Modul und fügt es zum Bot hinzu."""
    await bot.add_cog(MemberLists(bot))
    print("📋 MemberLists Modul wurde erfolgreich geladen!")
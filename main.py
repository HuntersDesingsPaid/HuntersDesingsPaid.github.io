"""
Discord Bot Main Module
Author: HuntersDesingsPaid
Version: 2.0.0
Last Updated: 2025-05-07 09:51:48 UTC
"""

import discord
import os
import importlib.util
import json
import logging
import asyncio
import sys
import traceback
import time
import signal
from typing import Dict, List, Optional, Any, Union, Callable
from datetime import datetime
from discord import app_commands
from discord.ext import commands, tasks

class BotConfig:
    """Hilfsklasse zum Laden und Verwalten der Bot-Konfiguration."""
    def __init__(self, config_path='config.json'):
        self.config_path = config_path
        self.config = self._load_config()
        self.last_modified = self._get_file_modified_time()
        self.user = "HuntersDesingsPaid"
        
    def _get_file_modified_time(self) -> float:
        """Gibt den Zeitstempel der letzten Änderung der Konfigurationsdatei zurück."""
        try:
            return os.path.getmtime(self.config_path)
        except OSError:
            return 0
        
    def _load_config(self) -> Dict[str, Any]:
        """Lädt die Konfiguration aus der Datei."""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            logging.error(f"❌ Fehler: Konfigurationsdatei '{self.config_path}' nicht gefunden.")
            self._create_example_config()
            logging.info(f"📝 Eine Beispielkonfiguration wurde unter '{self.config_path}' erstellt.")
            exit(1)
        except json.JSONDecodeError as e:
            logging.error(f"❌ Fehler: Ungültiges JSON-Format in '{self.config_path}': {str(e)}")
            exit(1)
    
    def _create_example_config(self) -> None:
        """Erstellt eine Beispielkonfigurationsdatei."""
        example_config = {
            "discord_token": "DEIN_DISCORD_TOKEN_HIER",
            "command_prefix": "!",
            "module_path": "modules",
            "enabled_modules": ["matchday_module"],
            "log_level": "INFO",
            "admin_users": [],
            "admin_roles": [],
            "activity_type": "playing",
            "activity_name": "mit Slash-Commands",
            "user": self.user,
            "timezone": "UTC",
            "matchday": {
                "image_size": {"width": 1024, "height": 1024},
                "background_color": "#292929",
                "text_color": "#ffffff"
            },
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(example_config, f, indent=4)
        except Exception as e:
            logging.error(f"❌ Fehler beim Erstellen der Beispielkonfiguration: {str(e)}")
    
    def get(self, key: str, default: Any = None) -> Any:
        """Gibt einen Konfigurationswert zurück."""
        return self.config.get(key, default)
    
    def set(self, key: str, value: Any) -> None:
        """Setzt einen Konfigurationswert und speichert die Konfiguration."""
        self.config[key] = value
        self.config["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.save()
    
    def save(self) -> bool:
        """Speichert die aktuelle Konfiguration in die Datei."""
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4)
            self.last_modified = self._get_file_modified_time()
            logging.info("💾 Konfiguration wurde gespeichert.")
            return True
        except Exception as e:
            logging.error(f"❌ Fehler beim Speichern der Konfiguration: {str(e)}")
            return False
    
    def reload(self) -> bool:
        """Lädt die Konfiguration neu, wenn die Datei geändert wurde."""
        current_modified = self._get_file_modified_time()
        if current_modified > self.last_modified:
            try:
                self.config = self._load_config()
                self.last_modified = current_modified
                logging.info("🔄 Konfiguration wurde neu geladen.")
                return True
            except Exception as e:
                logging.error(f"❌ Fehler beim Neuladen der Konfiguration: {str(e)}")
                return False
        return False
        
    def ensure_module_loaded_once(self, module_name: str) -> None:
        """Stellt sicher, dass ein Modul nur einmal in der Liste der aktivierten Module vorkommt."""
        if 'enabled_modules' not in self.config:
            self.config['enabled_modules'] = []
            
        if module_name not in self.config['enabled_modules']:
            self.config['enabled_modules'].append(module_name)
            self.save()
            logging.info(f"✅ Modul '{module_name}' zur Konfiguration hinzugefügt.")
            return
            
        if self.config['enabled_modules'].count(module_name) > 1:
            self.config['enabled_modules'] = [m for m in self.config['enabled_modules'] if m != module_name]
            self.config['enabled_modules'].append(module_name)
            logging.info(f"🔧 Doppelte Einträge für Modul '{module_name}' wurden bereinigt.")
            self.save()
                
    def check_duplicate_modules(self) -> None:
        """Überprüft die Konfiguration auf doppelte Module und korrigiert sie."""
        if 'enabled_modules' not in self.config:
            self.config['enabled_modules'] = ["matchday_module"]
            self.save()
            return
            
        seen = set()
        duplicates = set()
        unique_modules = []
        
        for module in self.config['enabled_modules']:
            if module in seen:
                duplicates.add(module)
            else:
                seen.add(module)
                unique_modules.append(module)
                
        if duplicates:
            self.config['enabled_modules'] = unique_modules
            logging.info(f"🔧 Doppelte Module in der Konfiguration gefunden und korrigiert: {', '.join(duplicates)}")
            self.save()

    def validate_matchday_config(self) -> bool:
        """Überprüft und korrigiert die Matchday-Modul-Konfiguration."""
        try:
            if 'enabled_modules' not in self.config:
                self.config['enabled_modules'] = []
            
            if 'matchday_module' not in self.config['enabled_modules']:
                self.config['enabled_modules'].append('matchday_module')
                logging.info("✅ Matchday-Modul wurde automatisch aktiviert.")
                
            if 'matchday' not in self.config:
                self.config['matchday'] = {
                    'image_size': {'width': 1024, 'height': 1024},
                    'background_color': '#292929',
                    'text_color': '#ffffff',
                    'last_updated': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
            
            self.save()
            return True
        except Exception as e:
            logging.error(f"❌ Fehler bei der Matchday-Konfiguration: {str(e)}")
            return False

class ModuleManager:
    """Verwaltet das Laden und Entladen von Bot-Modulen."""
    def __init__(self, bot, module_path='modules'):
        self.bot = bot
        self.module_path = module_path
        self.modules: Dict[str, Any] = {}
        self.loading_errors: List[str] = []
        self.module_dependencies: Dict[str, List[str]] = {}
        self.required_modules: List[str] = ["matchday_module"]
        self.loaded_cogs: List[str] = []
        
    async def load_modules(self, enabled_modules: List[str]) -> None:
        """Lädt alle aktivierten Module."""
        if not os.path.exists(self.module_path):
            os.makedirs(self.module_path)
            logging.warning(f"🔧 Modulordner '{self.module_path}' wurde erstellt.")
            return

        for required_module in self.required_modules:
            if required_module not in enabled_modules:
                enabled_modules.append(required_module)
                logging.info(f"📌 Erforderliches Modul '{required_module}' wurde hinzugefügt.")

        for module_name in self.required_modules:
            if module_name in enabled_modules:
                await self._load_module(module_name)

        for filename in os.listdir(self.module_path):
            if filename.endswith('.py'):
                module_name = filename[:-3]
                if module_name in enabled_modules and module_name not in self.modules:
                    await self._load_module(module_name)
        
        loaded_count = len(self.modules)
        logging.info(f"✅ {loaded_count} Module erfolgreich geladen.")
        if self.loading_errors:
            logging.warning(f"⚠️ {len(self.loading_errors)} Module konnten nicht geladen werden:")
            for error in self.loading_errors:
                logging.warning(f"  ↳ {error}")
    
    def check_module_requirements(self, module_name: str) -> bool:
        """Überprüft die Anforderungen für spezifische Module."""
        if module_name == "matchday_module":
            try:
                from PIL import Image, ImageDraw, ImageFont
                return True
            except ImportError:
                logging.error("❌ Fehler: PIL (Pillow) ist nicht installiert. Bitte installiere es mit 'pip install Pillow'")
                return False
        return True
    
    async def _load_module(self, module_name: str) -> bool:
        """Lädt ein einzelnes Modul."""
        if module_name in self.modules:
            logging.debug(f"🔄 Modul '{module_name}' ist bereits geladen.")
            return True
            
        if not self.check_module_requirements(module_name):
            return False

        try:
            filepath = os.path.join(self.module_path, f"{module_name}.py")
            if not os.path.exists(filepath):
                self.loading_errors.append(f"Modul '{module_name}' nicht gefunden unter '{filepath}'.")
                return False
                
            spec = importlib.util.spec_from_file_location(module_name, filepath)
            if not spec:
                self.loading_errors.append(f"Fehler beim Laden der Spezifikation für Modul '{module_name}'.")
                return False
                
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            if hasattr(module, 'DEPENDENCIES'):
                dependencies = getattr(module, 'DEPENDENCIES', [])
                self.module_dependencies[module_name] = dependencies
                
                for dependency in dependencies:
                    if dependency not in self.modules:
                        dependency_loaded = await self._load_module(dependency)
                        if not dependency_loaded:
                            self.loading_errors.append(
                                f"Modul '{module_name}' benötigt '{dependency}', welches nicht geladen werden konnte."
                            )
                            return False
            
            if hasattr(module, 'setup'):
                try:
                    cog_name = self._extract_cog_name(module_name, filepath)
                    
                    if cog_name and cog_name in self.loaded_cogs:
                        logging.warning(f"⚠️ Cog '{cog_name}' ist bereits geladen. Überspringe '{module_name}'.")
                        return False
                    
                    await module.setup(self.bot)
                    
                    if cog_name:
                        self.loaded_cogs.append(cog_name)
                    
                    self.modules[module_name] = module
                    logging.info(f"✅ Modul '{module_name}' erfolgreich geladen.")
                    return True
                    
                except discord.ClientException as e:
                    if "already loaded" in str(e):
                        import re
                        match = re.search(r"Cog named '(.+)' already loaded", str(e))
                        if match:
                            cog_name = match.group(1)
                            self.loaded_cogs.append(cog_name)
                            logging.warning(f"⚠️ Cog '{cog_name}' ist bereits geladen.")
                        return False
                    else:
                        raise
            else:
                self.loading_errors.append(f"Modul '{module_name}' hat keine 'setup'-Funktion.")
                return False
                
        except Exception as e:
            error_traceback = traceback.format_exc()
            self.loading_errors.append(f"Fehler beim Laden von '{module_name}': {str(e)}")
            logging.error(f"❌ Ausführlicher Fehler bei '{module_name}':\n{error_traceback}")
            return False
    def _extract_cog_name(self, module_name: str, filepath: str) -> Optional[str]:
        """Extrahiert den Cog-Namen aus der Moduldatei."""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
                
            import re
            
            class_match = re.search(r"class\s+(\w+)\s*\(\s*commands\.Cog\s*\)", content)
            if class_match:
                return class_match.group(1)
                
            add_cog_match = re.search(r"await\s+bot\.add_cog\s*\(\s*(\w+)\s*\(", content)
            if add_cog_match:
                return add_cog_match.group(1)
                
        except Exception:
            pass
            
        return None
    
    async def reload_module(self, module_name: str) -> bool:
        """Lädt ein bereits geladenes Modul neu."""
        if module_name in self.modules:
            dependent_modules = [
                mod_name for mod_name, dependencies in self.module_dependencies.items()
                if module_name in dependencies and mod_name in self.modules
            ]
            
            for dep_module in dependent_modules:
                await self.unload_module(dep_module)
            
            if hasattr(self.modules[module_name], 'teardown'):
                try:
                    await self.modules[module_name].teardown(self.bot)
                except Exception as e:
                    logging.error(f"❌ Fehler beim Herunterfahren von '{module_name}': {str(e)}")
            
            for command in list(self.bot.tree.get_commands()):
                if hasattr(command, 'module') and command.module == module_name:
                    self.bot.tree.remove_command(command.name)
            
            importlib.invalidate_caches()
            
            filepath = os.path.join(self.module_path, f"{module_name}.py")
            cog_name = self._extract_cog_name(module_name, filepath)
            if cog_name and cog_name in self.loaded_cogs:
                self.loaded_cogs.remove(cog_name)
                
            del self.modules[module_name]
            result = await self._load_module(module_name)
            
            for dep_module in dependent_modules:
                await self._load_module(dep_module)
            
            if result:
                try:
                    await self.bot.tree.sync()
                except discord.HTTPException as e:
                    logging.error(f"❌ Fehler beim Synchronisieren der Befehle: {str(e)}")
            
            return result
        return False
    
    async def unload_module(self, module_name: str) -> bool:
        """Entlädt ein Modul."""
        if module_name in self.modules:
            dependent_modules = [
                mod_name for mod_name, dependencies in self.module_dependencies.items()
                if module_name in dependencies and mod_name in self.modules
            ]
            
            if dependent_modules and module_name not in self.required_modules:
                logging.warning(
                    f"⚠️ '{module_name}' kann nicht entladen werden. Abhängige Module: {', '.join(dependent_modules)}"
                )
                return False
            
            if module_name in self.required_modules:
                logging.warning(f"⚠️ '{module_name}' ist ein erforderliches Modul.")
                return False
            
            if hasattr(self.modules[module_name], 'teardown'):
                try:
                    await self.modules[module_name].teardown(self.bot)
                except Exception as e:
                    logging.error(f"❌ Fehler beim Herunterfahren von '{module_name}': {str(e)}")
            
            for command in list(self.bot.tree.get_commands()):
                if hasattr(command, 'module') and command.module == module_name:
                    self.bot.tree.remove_command(command.name)
            
            filepath = os.path.join(self.module_path, f"{module_name}.py")
            cog_name = self._extract_cog_name(module_name, filepath)
            if cog_name and cog_name in self.loaded_cogs:
                self.loaded_cogs.remove(cog_name)
            
            del self.modules[module_name]
            
            try:
                await self.bot.tree.sync()
            except discord.HTTPException as e:
                logging.error(f"❌ Fehler beim Synchronisieren der Befehle: {str(e)}")
            
            logging.info(f"🗑️ Modul '{module_name}' erfolgreich entladen.")
            return True
        return False
    
    async def load_module(self, module_name: str) -> bool:
        """Lädt ein neues Modul."""
        if module_name in self.modules:
            logging.info(f"🔄 Modul '{module_name}' ist bereits geladen.")
            return True
        
        result = await self._load_module(module_name)
        if result:
            try:
                await self.bot.tree.sync()
            except discord.HTTPException as e:
                logging.error(f"❌ Fehler beim Synchronisieren der Befehle: {str(e)}")
        
        return result
    
    async def dispatch_event(self, event_name: str, *args, **kwargs) -> None:
        """Ruft eine Event-Funktion in allen Modulen auf."""
        for module_name, module in self.modules.items():
            if hasattr(module, event_name):
                try:
                    event_handler = getattr(module, event_name)
                    await event_handler(*args, **kwargs)
                except Exception as e:
                    error_traceback = traceback.format_exc()
                    logging.error(f"❌ Fehler in '{module_name}' bei Event '{event_name}': {str(e)}")
                    logging.debug(f"🔍 Ausführlicher Fehler in '{module_name}':\n{error_traceback}")

class DiscordBot(commands.Bot):
    """Hauptklasse für den Discord Bot mit erweiterter Funktionalität."""
    def __init__(self, config: BotConfig):
        self.config = config
        self.start_time = datetime.now()
        self.shutdown_flag = False
        
        # Konfiguriere Intents
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.guilds = True
        intents.reactions = True
        
        # Initialisiere den Bot
        command_prefix = config.get('command_prefix', '!')
        super().__init__(command_prefix=command_prefix, intents=intents, help_command=None)
        
        # Initialisiere Manager und Helper
        self.module_manager = ModuleManager(self, config.get('module_path', 'modules'))
        self.emoji_helper = None
        
        # Registriere Basis-Befehle und Events
        self._register_base_commands()
        self._register_base_events()
        
        # Starte Hintergrundaufgaben
        self.check_config_updates.start()
    
    def _register_base_commands(self) -> None:
        """Registriert grundlegende Bot-Befehle als Slash-Commands."""
        admin_group = app_commands.Group(name="admin", description="Admin-Befehle für die Bot-Verwaltung")
        
        @admin_group.command(name="modules", description="Zeigt alle geladenen Module an")
        @app_commands.checks.has_permissions(administrator=True)
        async def list_modules(interaction: discord.Interaction):
            if not self.module_manager.modules:
                await interaction.response.send_message("⚠️ Keine Module geladen.", ephemeral=True)
                return
            
            embed = discord.Embed(
                title="📦 Geladene Module",
                description="Folgende Module sind derzeit aktiv:",
                color=discord.Color.green(),
                timestamp=datetime.now()
            )
            
            independent_modules = []
            dependent_modules = {}
            
            for name in self.module_manager.modules.keys():
                if name in self.module_manager.module_dependencies and self.module_manager.module_dependencies[name]:
                    deps = self.module_manager.module_dependencies[name]
                    dependent_modules[name] = deps
                else:
                    independent_modules.append(name)
            
            if independent_modules:
                embed.add_field(
                    name="🔹 Unabhängige Module",
                    value="\n".join([f"• `{name}`" for name in sorted(independent_modules)]),
                    inline=False
                )
            
            if dependent_modules:
                embed.add_field(
                    name="🔗 Module mit Abhängigkeiten",
                    value="\n".join([
                        f"• `{name}` (benötigt: {', '.join(['`'+d+'`' for d in deps])})" 
                        for name, deps in sorted(dependent_modules.items())
                    ]),
                    inline=False
                )
            
            embed.set_footer(text=f"Insgesamt {len(self.module_manager.modules)} Module geladen")
            await interaction.response.send_message(embed=embed, ephemeral=True)
        
        @admin_group.command(name="reload", description="Lädt ein Modul neu")
        @app_commands.checks.has_permissions(administrator=True)
        @app_commands.describe(module_name="Name des neu zu ladenden Moduls")
        async def reload_module(interaction: discord.Interaction, module_name: str):
            await interaction.response.defer(ephemeral=True)
            if await self.module_manager.reload_module(module_name):
                embed = discord.Embed(
                    title="🔄 Modul neu geladen",
                    description=f"Modul `{module_name}` wurde erfolgreich neu geladen.",
                    color=discord.Color.green(),
                    timestamp=datetime.now()
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                embed = discord.Embed(
                    title="❌ Fehler beim Neuladen",
                    description=f"Modul `{module_name}` konnte nicht neu geladen werden.",
                    color=discord.Color.red(),
                    timestamp=datetime.now()
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
        
        @admin_group.command(name="unload", description="Entlädt ein Modul")
        @app_commands.checks.has_permissions(administrator=True)
        @app_commands.describe(module_name="Name des zu entladenden Moduls")
        async def unload_module(interaction: discord.Interaction, module_name: str):
            await interaction.response.defer(ephemeral=True)
            if await self.module_manager.unload_module(module_name):
                embed = discord.Embed(
                    title="🗑️ Modul entladen",
                    description=f"Modul `{module_name}` wurde erfolgreich entladen.",
                    color=discord.Color.green(),
                    timestamp=datetime.now()
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                embed = discord.Embed(
                    title="❌ Fehler beim Entladen",
                    description=f"Modul `{module_name}` konnte nicht entladen werden.",
                    color=discord.Color.red(),
                    timestamp=datetime.now()
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
        
        @admin_group.command(name="load", description="Lädt ein Modul")
        @app_commands.checks.has_permissions(administrator=True)
        @app_commands.describe(module_name="Name des zu ladenden Moduls")
        async def load_module(interaction: discord.Interaction, module_name: str):
            await interaction.response.defer(ephemeral=True)
            if await self.module_manager.load_module(module_name):
                embed = discord.Embed(
                    title="📥 Modul geladen",
                    description=f"Modul `{module_name}` wurde erfolgreich geladen.",
                    color=discord.Color.green(),
                    timestamp=datetime.now()
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                embed = discord.Embed(
                    title="❌ Fehler beim Laden",
                    description=f"Modul `{module_name}` konnte nicht geladen werden.",
                    color=discord.Color.red(),
                    timestamp=datetime.now()
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
        
        @admin_group.command(name="status", description="Zeigt Statusinformationen zum Bot an")
        @app_commands.checks.has_permissions(administrator=True)
        async def bot_status(interaction: discord.Interaction):
            uptime = datetime.now() - self.start_time
            days, remainder = divmod(uptime.total_seconds(), 86400)
            hours, remainder = divmod(remainder, 3600)
            minutes, seconds = divmod(remainder, 60)
            
            uptime_str = f"{int(days)}d {int(hours)}h {int(minutes)}m {int(seconds)}s"
            
            embed = discord.Embed(
                title="🤖 Bot Status",
                color=discord.Color.blue(),
                timestamp=datetime.now()
            )
            
            embed.add_field(name="⏱️ Uptime", value=uptime_str, inline=False)
            embed.add_field(name="📦 Geladene Module", value=str(len(self.module_manager.modules)), inline=True)
            embed.add_field(name="🌐 Verbundene Server", value=str(len(self.guilds)), inline=True)
            embed.add_field(name="📚 Discord.py Version", value=discord.__version__, inline=True)
            embed.add_field(name="🐍 Python Version", 
                          value=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}", 
                          inline=True)
            
            if len(self.guilds) <= 10:
                guild_list = "\n".join([f"• {guild.name} (ID: {guild.id})" for guild in self.guilds])
                embed.add_field(name="📋 Server Liste", value=guild_list or "Keine Server", inline=False)
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        
        @admin_group.command(name="shutdown", description="Fährt den Bot sicher herunter")
        @app_commands.checks.has_permissions(administrator=True)
        async def shutdown_bot(interaction: discord.Interaction):
            embed = discord.Embed(
                title="🛑 Bot wird heruntergefahren",
                description="Der Bot wird jetzt sicher heruntergefahren...",
                color=discord.Color.red(),
                timestamp=datetime.now()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            logging.info(f"🛑 Bot-Shutdown wurde von {interaction.user.name} ({interaction.user.id}) initiiert.")
            self.shutdown_flag = True
            await self.close()
        
        self.tree.add_command(admin_group)
        
        @self.tree.command(name="help", description="Zeigt Hilfe zu den verfügbaren Befehlen an")
        async def help_command(interaction: discord.Interaction):
            embed = discord.Embed(
                title="📚 Bot-Hilfe",
                description="Hier sind die verfügbaren Befehle:",
                color=discord.Color.blue(),
                timestamp=datetime.now()
            )
            
            commands_list = {}
            for command in self.tree.get_commands():
                if isinstance(command, app_commands.Group):
                    group_name = command.name
                    if group_name not in commands_list:
                        commands_list[group_name] = []
                    
                    for subcommand in command.commands:
                        commands_list[group_name].append(
                            f"• `/{group_name} {subcommand.name}` - {subcommand.description}"
                        )
                else:
                    if "Allgemein" not in commands_list:
                        commands_list["Allgemein"] = []
                    commands_list["Allgemein"].append(f"• `/{command.name}` - {command.description}")
            
            for category, commands in commands_list.items():
                if commands:
                    category_emoji = "🔹"
                    if category.lower() == "admin":
                        category_emoji = "⚙️"
                    elif category.lower() == "allgemein":
                        category_emoji = "🔍"
                    elif category.lower() == "matchday":
                        category_emoji = "🎮"
                    
                    embed.add_field(
                        name=f"{category_emoji} {category.capitalize()}",
                        value="\n".join(commands),
                        inline=False
                    )
            
            embed.set_footer(text=f"Angefordert von {interaction.user.name}")
            await interaction.response.send_message(embed=embed, ephemeral=True)
    
    def _register_base_events(self) -> None:
        """Registriert grundlegende Event-Handler."""
        @self.event
        async def on_ready():
            logging.info(f"🚀 Bot ist bereit! Eingeloggt als {self.user.name} (ID: {self.user.id})")
            logging.info(f"🌐 Bot ist auf {len(self.guilds)} Servern aktiv")
            
            activity_type = self.config.get('activity_type', 'playing')
            activity_name = self.config.get('activity_name', 'mit Slash-Commands')
            
            activity = None
            if activity_type.lower() == 'playing':
                activity = discord.Game(name=activity_name)
            elif activity_type.lower() == 'listening':
                activity = discord.Activity(type=discord.ActivityType.listening, name=activity_name)
            elif activity_type.lower() == 'watching':
                activity = discord.Activity(type=discord.ActivityType.watching, name=activity_name)
            
            if activity:
                await self.change_presence(activity=activity)
        
        @self.event
        async def on_guild_join(guild):
            logging.info(f"✅ Bot wurde zu Server hinzugefügt: {guild.name} (ID: {guild.id})")
            await self.module_manager.dispatch_event('on_guild_join', guild, self)
        
        @self.event
        async def on_guild_remove(guild):
            logging.info(f"❌ Bot hat Server verlassen: {guild.name} (ID: {guild.id})")
            await self.module_manager.dispatch_event('on_guild_remove', guild, self)
        
        @self.event
        async def on_error(event, *args, **kwargs):
            error_traceback = traceback.format_exc()
            logging.error(f"⚠️ Fehler im Event {event}: {error_traceback}")
    
    @tasks.loop(minutes=5.0)
    async def check_config_updates(self):
        """Überprüft regelmäßig, ob die Konfigurationsdatei aktualisiert wurde."""
        if self.config.reload():
            logging.info("🔄 Konfiguration wurde aktualisiert. Wende Änderungen an...")
            
            activity_type = self.config.get('activity_type', 'playing')
            activity_name = self.config.get('activity_name', 'mit Slash-Commands')
            
            activity = None
            if activity_type.lower() == 'playing':
                activity = discord.Game(name=activity_name)
            elif activity_type.lower() == 'listening':
                activity = discord.Activity(type=discord.ActivityType.listening, name=activity_name)
            elif activity_type.lower() == 'watching':
                activity = discord.Activity(type=discord.ActivityType.watching, name=activity_name)
            
            if activity:
                await self.change_presence(activity=activity)
    
    @check_config_updates.before_loop
    async def before_check_config(self):
        """Wartet, bis der Bot bereit ist, bevor die Aufgabe gestartet wird."""
        await self.wait_until_ready()
    
    async def setup_hook(self):
        """Wird beim Start des Bots ausgeführt."""
        # Erstelle erforderliche Verzeichnisse
        required_paths = [
            "modules",
            "modules/matchday",
            "modules/matchday/zwischenspeicher",
            "logs"
        ]
        
        for path in required_paths:
            os.makedirs(path, exist_ok=True)
            
        self.emoji_helper = None
        
        # Lade alle aktivierten Module
        enabled_modules = self.config.get('enabled_modules', [])
        
        # Stelle sicher, dass matchday_module aktiviert ist
        if 'matchday_module' not in enabled_modules:
            enabled_modules.append('matchday_module')
            self.config.set('enabled_modules', enabled_modules)
            
        # Validiere Matchday-Konfiguration
        self.config.validate_matchday_config()
        
        await self.module_manager.load_modules(enabled_modules)
        
        try:
            await self.tree.sync()
            logging.info("✅ Slash-Commands wurden mit Discord synchronisiert.")
        except discord.HTTPException as e:
            logging.error(f"❌ Fehler beim Synchronisieren der Slash-Commands: {str(e)}")
    
    async def on_message(self, message):
        """Verarbeitet eingehende Nachrichten."""
        if message.author.bot:
            return
        
        await self.process_commands(message)
        await self.module_manager.dispatch_event('on_message', message, self)
    
    async def on_interaction(self, interaction):
        """Verarbeitet eingehende Interaktionen."""
        if interaction.type == discord.InteractionType.application_command:
            await self.module_manager.dispatch_event('on_slash_command', interaction, self)
    
    async def close(self):
        """Überschreibt die close-Methode für einen sauberen Shutdown."""
        logging.info("🛑 Bot wird heruntergefahren...")
        
        self.check_config_updates.cancel()
        
        for module_name in list(self.module_manager.modules.keys()):
            if hasattr(self.module_manager.modules[module_name], 'teardown'):
                try:
                    await self.module_manager.modules[module_name].teardown(self)
                    logging.info(f"✅ Modul '{module_name}' erfolgreich heruntergefahren.")
                except Exception as e:
                    logging.error(f"❌ Fehler beim Herunterfahren von '{module_name}': {str(e)}")
        
        await super().close()

def setup_logging():
    """Richtet das Logging-System ein."""
    if not os.path.exists('logs'):
        os.makedirs('logs')
    
    timestamp = datetime.now().strftime("%Y-%m-%d")
    log_filename = f"logs/bot_{timestamp}.log"
    
    log_format = '%(asctime)s - %(levelname)s - %(message)s'
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        handlers=[
            logging.FileHandler(log_filename, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    
    logging.getLogger('discord').setLevel(logging.WARNING)
    logging.getLogger('discord.http').setLevel(logging.WARNING)
    logging.getLogger('discord.gateway').setLevel(logging.WARNING)
    
    logging.info("=" * 60)
    logging.info(f"🚀 Bot-Logging gestartet am {datetime.now().strftime('%d.%m.%Y um %H:%M:%S')}")
    logging.info("=" * 60)

def handle_sigterm(signum, frame):
    """Behandelt SIGTERM-Signale für einen sauberen Shutdown."""
    logging.info("🛑 SIGTERM-Signal empfangen. Bot wird heruntergefahren...")
    asyncio.create_task(shutdown())

async def shutdown():
    """Fährt den Bot sauber herunter."""
    if 'bot' in globals():
        logging.info("🔽 Führe sauberen Shutdown durch...")
        await bot.close()
    
    logging.info("👋 Bot-Prozess wird beendet.")
    sys.exit(0)

async def main():
    """Hauptfunktion zum Starten des Bots."""
    global bot
    
    setup_logging()
    
    signal.signal(signal.SIGINT, lambda s, f: asyncio.create_task(shutdown()))
    if hasattr(signal, 'SIGTERM'):
        signal.signal(signal.SIGTERM, handle_sigterm)
    
    print("\n" + "=" * 60)
    print("🤖 ZEALOX BOT STARTER".center(60))
    print("=" * 60)
    
    retry_count = 0
    max_retries = 5
    retry_delay = 5
    
    while retry_count < max_retries:
        try:
            config = BotConfig()
            
            config.check_duplicate_modules()
            config.validate_matchday_config()
            
            token = config.get('discord_token')
            
            if not token or token == "DEIN_DISCORD_TOKEN_HIER":
                logging.error("❌ Fehler: Discord-Token nicht gefunden oder nicht gesetzt.")
                print("\n❌ Fehler: Discord-Token nicht gefunden oder nicht gesetzt.")
                print("   Bitte trage dein Token in der config.json ein und starte neu.")
                return
            
            enabled_modules = config.get('enabled_modules', [])
            print(f"📋 Konfiguration geladen:")
            print(f"   • Prefix: {config.get('command_prefix', '!')}")
            print(f"   • Aktivierte Module: {len(enabled_modules)}")
            if enabled_modules:
                print(f"     {', '.join(enabled_modules)}")
            
            print(f"\n🔄 Initialisiere Bot...")
            bot = DiscordBot(config)
            
            print(f"🔌 Verbinde mit Discord...")
            async with bot:
                await bot.start(token)
                
            if bot.shutdown_flag:
                logging.info("✅ Bot wurde ordnungsgemäß heruntergefahren.")
                print("\n✅ Bot wurde ordnungsgemäß heruntergefahren.")
                break
            else:
                logging.warning("⚠️ Bot wurde unerwartet getrennt. Versuche Wiederverbindung...")
                print(f"\n⚠️ Bot wurde unerwartet getrennt. Versuche Wiederverbindung...")
                retry_count += 1
                await asyncio.sleep(retry_delay)
                
        except discord.LoginFailure:
            logging.error("❌ Fehler: Ungültiges Discord-Token.")
            print("\n❌ Fehler: Ungültiges Discord-Token.")
            break
            
        except Exception as e:
            error_traceback = traceback.format_exc()
            logging.error(f"❌ Kritischer Fehler: {str(e)}")
            logging.debug(f"🔍 Ausführlicher Fehler:\n{error_traceback}")
            
            print(f"\n❌ Kritischer Fehler: {str(e)}")
            
            retry_count += 1
            if retry_count < max_retries:
                logging.info(f"🔄 Neustart in {retry_delay}s... (Versuch {retry_count}/{max_retries})")
                print(f"🔄 Neustart in {retry_delay}s... (Versuch {retry_count}/{max_retries})")
                await asyncio.sleep(retry_delay)
                retry_delay *= 2
            else:
                logging.error("❌ Maximale Anzahl an Wiederverbindungsversuchen erreicht.")
                print("\n❌ Maximale Anzahl an Wiederverbindungsversuchen erreicht.")
                break
    
    print("\n" + "=" * 60)
    print("👋 ZEALOX BOT BEENDET".center(60))
    print("=" * 60 + "\n")

if __name__ == "__main__":
    asyncio.run(main())

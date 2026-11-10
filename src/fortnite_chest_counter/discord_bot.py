"""Discord Gateway lifecycle and slash commands for local Group totals."""

import asyncio
from dataclasses import replace
import threading

import discord
from discord import app_commands

from fortnite_chest_counter.discord_group import GROUP_TYPE_LABELS, GroupStore


def register_commands(tree, guild, totals, ready):
    async def reply(interaction, title, detail):
        send = interaction.followup.send if interaction.response.is_done() else interaction.response.send_message
        if interaction.app_permissions.embed_links:
            await send(embed=discord.Embed(title=title, description=detail, color=0x5865F2))
        else:
            await send(f"**{title}**\n{detail}"[:2000])

    async def error(interaction, message):
        send = interaction.followup.send if interaction.response.is_done() else interaction.response.send_message
        await send(message, ephemeral=True)

    async def check(interaction, *, manage_guild=False):
        if interaction.guild_id != guild.id:
            await error(interaction, "These commands are only available in the configured server.")
            return False
        if manage_guild and not interaction.permissions.manage_guild:
            await error(interaction, "You need Manage Server to change chest totals.")
            return False
        if not ready():
            await error(interaction, "The bot is catching up with the Group feed. Try again in a moment.")
            return False
        return True

    async def autocomplete(interaction, current):
        if interaction.guild_id != guild.id or not ready():
            return []
        try:
            rows = await asyncio.to_thread(totals.leaderboard)
            return [
                app_commands.Choice(name=row.name, value=row.name)
                for row in rows
                if current.casefold() in row.name.casefold() and len(row.name) <= 100
            ][:25]
        except (OSError, ValueError):
            return []

    @tree.command(guild=guild, description="Show the Group chest totals")
    @app_commands.describe(player="Leave empty to count everyone")
    @app_commands.autocomplete(player=autocomplete)
    async def chests(interaction: discord.Interaction, player: str | None = None):
        if not await check(interaction):
            return
        try:
            row = await asyncio.to_thread(totals.stats, player)
        except ValueError as exc:
            await error(interaction, str(exc))
            return
        details = [f"**{discord.utils.escape_markdown(row.name)}** · {row.total:,} chests · {row.matches:,} matches"]
        if row.certain is not None:
            details.append(f"Recorded breakdown: {row.certain:,} certain · {row.confirmed_total - row.certain:,} estimated")
        if row.chest_types:
            details.append(" · ".join(f"{label}: {row.chest_types[key]:,}" for key, label in GROUP_TYPE_LABELS.items()
                                      if key in row.chest_types))
        if row.adjustment:
            details.append(f"Manual adjustment: {row.adjustment:+,}")
        await reply(interaction, "Chests opened", "\n".join(details))

    @tree.command(guild=guild, description="Rank players by chests opened")
    async def leaderboard(interaction: discord.Interaction):
        if not await check(interaction):
            return
        rows = (await asyncio.to_thread(totals.leaderboard))[:10]
        lines = [f"**{rank}.** {discord.utils.escape_markdown(row.name)} · {row.total:,} chests · {row.matches:,} matches"
                 for rank, row in enumerate(rows, 1)]
        detail = "\n".join(lines) or "No players in saved Group matches yet."
        if len(detail) > 1950:
            detail = detail[:1950].rsplit("\n", 1)[0] + "\n…"
        await reply(interaction, "Chest leaderboard", detail)

    async def adjust(interaction, player, amount):
        if not await check(interaction, manage_guild=True):
            return
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            name, total = await asyncio.to_thread(totals.adjust, player, amount)
        except ValueError as exc:
            await error(interaction, str(exc))
            return
        title = "Chest total reset" if amount is None else "Chest total updated"
        await reply(interaction, title, f"**{discord.utils.escape_markdown(name)}** · {total:,}")

    @tree.command(guild=guild, description="Correct a player's total with a positive or negative count")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.autocomplete(player=autocomplete)
    async def add(interaction: discord.Interaction, player: str, amount: int):
        await adjust(interaction, player, amount)

    @tree.command(guild=guild, description="Reset a player's chest total")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.autocomplete(player=autocomplete)
    async def reset(interaction: discord.Interaction, player: str):
        await adjust(interaction, player, None)

    @tree.error
    async def on_command_error(interaction, _):
        await error(interaction, "The Discord command could not finish. Check the app and try again.")


class _SetupError(Exception):
    pass


class GuildBot(discord.Client):
    def __init__(self, config, totals, status, webhook=None):
        shared = webhook is not None
        super().__init__(intents=discord.Intents(guilds=True, guild_messages=shared, message_content=shared),
                         allowed_mentions=discord.AllowedMentions.none())
        self.config = config
        self.totals = totals
        self._status_changed = status
        self.webhook = webhook
        self.tree = app_commands.CommandTree(self, fallback_to_global=False)
        self.feed_channel = None
        self._feed_lock = asyncio.Lock()
        self._feed_ready = False
        self._connection_epoch = 0
        self.failure = None

    async def setup_hook(self):
        if self.config.application_id and int(self.config.application_id) != self.application_id:
            raise _SetupError("The bot token does not match the saved Application ID.")
        if self.webhook:
            try:
                partial = discord.Webhook.partial(int(self.webhook.id), self.webhook.token, client=self)
                webhook = await partial.fetch(prefer_auth=False)
            except (discord.NotFound, discord.Forbidden):
                raise _SetupError("Discord rejected the saved Group webhook. Check the webhook in Group.") from None
            if webhook.channel_id is None or webhook.guild_id is None:
                raise _SetupError("Use an incoming webhook attached to a Discord server text channel.")
            try:
                self.feed_channel = await self.fetch_channel(webhook.channel_id)
            except (discord.NotFound, discord.Forbidden):
                raise _SetupError("The bot cannot see the Group feed channel. Check View Channel.") from None
            if not isinstance(self.feed_channel, discord.TextChannel):
                raise _SetupError("Use a Group webhook attached to a Discord text channel.")

        if self.feed_channel is None:
            raise _SetupError("Save the Group webhook before starting the bot.")
        guild = discord.Object(self.feed_channel.guild.id)
        register_commands(self.tree, guild, self.totals, lambda: self._feed_ready)
        for command in self.tree.get_commands(guild=guild):
            # Guild POST upserts this name/type. Bulk sync would delete unrelated commands.
            await self.http.upsert_guild_command(self.application_id, guild.id, command.to_dict(self.tree))

    async def on_ready(self):
        epoch = self._connection_epoch
        if self.feed_channel is not None:
            cached_channel = self.get_channel(self.feed_channel.id)
            if cached_channel is not None and cached_channel.guild.me is not None:
                permissions = cached_channel.permissions_for(cached_channel.guild.me)
                if not permissions.read_message_history:
                    self.failure = "Grant the bot Read Message History in the Group feed channel."
                    await self.close()
                    return
            await self._catch_up()
        if not self.failure and epoch == self._connection_epoch:
            self._feed_ready = True
            self._status_changed("online", f"Connected as {self.user}.")

    async def on_resumed(self):
        await self.on_ready()

    async def on_disconnect(self):
        self._connection_epoch += 1
        self._feed_ready = False
        self._status_changed("connecting", "Reconnecting to Discord…")

    async def on_message(self, message):
        if (self.feed_channel and message.channel.id == self.feed_channel.id
                and str(message.webhook_id) == self.totals.webhook_id):
            await self._catch_up(through=message)

    async def _catch_up(self, through=None):
        # Serialize history and live delivery. Never move the cursor past a
        # message before processing the older messages in the same channel.
        async with self._feed_lock:
            try:
                last = await asyncio.to_thread(self.totals.cursor, self.feed_channel.id)
                if through is not None and through.id <= last:
                    return
                async for message in self.feed_channel.history(limit=None, after=discord.Object(last),
                                                               before=through, oldest_first=True):
                    if str(message.webhook_id) == self.totals.webhook_id:
                        await asyncio.to_thread(self.totals.ingest, message)
                    last = message.id
                if through is not None:
                    await asyncio.to_thread(self.totals.ingest, through)
                elif last:
                    await asyncio.to_thread(self.totals.advance_cursor, self.feed_channel.id, last)
            except discord.Forbidden:
                self.failure = "Grant the bot Read Message History in the Group feed channel."
            except Exception:
                self.failure = "Could not read shared Group contributions. Check the feed channel and local state."
            if self.failure:
                self._feed_ready = False
                await self.close()


class BotRunner:
    """Own one cancellable Gateway session on a background thread."""

    def __init__(self, config, webhook, changed):
        self.config = config
        self.webhook = webhook
        self._totals = GroupStore(webhook.id if webhook else "")
        self._changed = changed
        self._lock = threading.Lock()
        self._status = ("connecting", "Connecting to Discord…")
        self._session = None
        self.report_config = None
        self._thread = threading.Thread(target=self._run, daemon=True, name="discord-gateway")

    @property
    def status(self):
        with self._lock:
            return self._status

    def start(self):
        self._thread.start()

    def stop(self, *, timeout=None):
        with self._lock:
            if self._status[0] not in ("stopped", "error", "stopping"):
                self._status = ("stopping", "Disconnecting from Discord…")
                if self._session is not None:
                    loop, task = self._session
                    loop.call_soon_threadsafe(task.cancel)
        if timeout is not None:
            self._thread.join(timeout)

    def _update(self, state, detail, channel_id=None):
        with self._lock:
            if self._status[0] == "stopping":
                return
            self._status = (state, detail)
            if channel_id is not None:
                self.report_config = replace(self.config, channel=str(channel_id))
        self._changed()

    async def _connect(self):
        def status_changed(state, detail):
            self._update(state, detail, bot.feed_channel.id if bot.feed_channel is not None else None)

        async with GuildBot(self.config, self._totals, status_changed, self.webhook) as bot:
            with self._lock:
                if self._status[0] == "stopping":
                    return
                self._session = asyncio.get_running_loop(), asyncio.create_task(bot.start(self.config.token))
            try:
                await self._session[1]
                if bot.failure:
                    raise _SetupError(bot.failure)
            finally:
                with self._lock:
                    self._session = None

    def _run(self):
        result = ("stopped", "The bot is off.")
        try:
            asyncio.run(self._connect())
        except asyncio.CancelledError:
            pass
        except discord.LoginFailure:
            result = ("error", "Discord rejected the bot token. Check the saved setup.")
        except discord.PrivilegedIntentsRequired:
            result = ("error", "Enable Message Content Intent on the Discord Developer Portal's Bot page.")
        except _SetupError as exc:
            result = ("error", str(exc))
        except discord.Forbidden:
            result = ("error", "Discord denied command registration. Check the bot's server installation.")
        except Exception:
            result = ("error", "Could not connect to Discord. Check your connection and saved setup.")
        finally:
            with self._lock:
                if self._status[0] == "stopping":
                    result = ("stopped", "The bot is off.")
                self._status = result
            self._changed()

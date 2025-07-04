import discord
from discord.ext import commands, tasks
import requests
from datetime import datetime

class ExchangeRates(commands.Cog):
    """Automatic LTC/USD rate updater"""

    def __init__(self, bot):
        self.bot = bot
        self.current_rate = None
        self.last_update = None
        self.rate_message = None  # For editing the display message
        self.update_rates.start()

    @tasks.loop(minutes=5)
    async def update_rates(self):
        """Fetch current LTC/USD rate every 5 minutes"""
        try:
            # Get fresh rate from API
            response = requests.get(
                self.bot.config["exchange_rate_api"],
                timeout=10
            )
            response.raise_for_status()
            new_rate = response.json()["litecoin"]["usd"]

            # Only update if rate changed
            if self.current_rate != new_rate:
                self.current_rate = new_rate
                self.last_update = datetime.now()

                # Update the persistent rate message
                if self.rate_message:
                    await self.rate_message.edit(
                        content=f"💱 1 LTC = ${new_rate:.2f} (Updated: {self.last_update.strftime('%H:%M')})"
                    )
                else:
                    channel = self.bot.get_channel(int(self.bot.config["rate_channel_id"]))
                    self.rate_message = await channel.send(
                        f"💱 1 LTC = ${new_rate:.2f}"
                    )

                # Update all active deals
                for deal in self.bot.active_deals.values():
                    if "amount_usd" in deal:
                        deal["amount_ltc"] = deal["amount_usd"] / new_rate

        except Exception as e:
            print(f"Rate update failed: {e}")

    @update_rates.before_loop
    async def before_update(self):
        """Ensure bot is ready before starting updates"""
        await self.bot.wait_until_ready()

    @commands.command()
    @commands.is_owner()
    async def forcerate(self, ctx):
        """Manually trigger rate update"""
        await self.update_rates()
        await ctx.send(f"Rate force-updated to: 1 LTC = ${self.current_rate:.2f}")

async def setup(bot):
    """Add cog to bot"""
    await bot.add_cog(ExchangeRates(bot))

import discord
from discord.ext import commands, tasks
from discord import ui, ButtonStyle, Embed
import asyncio
import json
import os
from datetime import datetime
from utils import *
from sochain import check_payment

# Load config
with open('config.json') as f:
    config = json.load(f)

intents = discord.Intents.all()
bot = commands.Bot(command_prefix='$', intents=intents)
bot.config = config
active_deals = {}

class PaymentTracker:
    def __init__(self):
        self.tracking_messages = {}

    async def update_status(self, channel, payment):
        deal = active_deals[channel.id]
        progress = format_progress(payment['confirmations'])
        
        embed = Embed(
            title=f"Payment Status ({payment['confirmations']}/6)",
            description=f"```{progress}```\nTXID: `{payment['txid']}`",
            color=0x5865F2
        )
        
        if channel.id in self.tracking_messages:
            await self.tracking_messages[channel.id].edit(embed=embed)
        else:
            self.tracking_messages[channel.id] = await channel.send(embed=embed)
        
        if payment['confirmations'] >= 6:
            await self.tracking_messages[channel.id].delete()
            del self.tracking_messages[channel.id]
            await show_release_options(channel)

payment_tracker = PaymentTracker()

class RoleView(ui.View):
    def __init__(self, channel_id):
        super().__init__(timeout=3600)
        self.channel_id = channel_id
        self.user_roles = {}

    @ui.button(label="Sender", style=ButtonStyle.green)
    async def sender_btn(self, interaction, button):
        deal = active_deals[self.channel_id]
        if deal.get('sender') == interaction.user:
            return
        deal['sender'] = interaction.user
        await interaction.response.send_message(
            embed=Embed(
                description=f"{interaction.user.mention} is now Sender",
                color=0x00FF00
            ),
            ephemeral=True
        )
        await self.check_roles(interaction)

    @ui.button(label="Receiver", style=ButtonStyle.blurple)
    async def receiver_btn(self, interaction, button):
        deal = active_deals[self.channel_id]
        if deal.get('receiver') == interaction.user:
            return
        deal['receiver'] = interaction.user
        await interaction.response.send_message(
            embed=Embed(
                description=f"{interaction.user.mention} is now Receiver",
                color=0x00FF00
            ),
            ephemeral=True
        )
        await self.check_roles(interaction)

    async def check_roles(self, interaction):
        deal = active_deals[self.channel_id]
        if deal.get('sender') and deal.get('receiver'):
            await interaction.channel.send(
                embed=Embed(
                    title="Roles Confirmed",
                    description="Both roles have been assigned!",
                    color=0x00FF00
                ),
                view=ConfirmView("roles", self.channel_id)
            )

class ConfirmView(ui.View):
    def __init__(self, confirm_type, channel_id):
        super().__init__(timeout=3600)
        self.confirm_type = confirm_type
        self.channel_id = channel_id
        self.confirmed = set()

    @ui.button(label="Confirm", style=ButtonStyle.green)
    async def confirm(self, interaction, button):
        deal = active_deals[self.channel_id]
        if interaction.user.id not in [deal['sender'].id, deal['receiver'].id]:
            return await interaction.response.send_message(
                "❌ Only deal participants can confirm!",
                ephemeral=True
            )
        
        self.confirmed.add(interaction.user.id)
        await interaction.response.send_message(
            embed=Embed(
                description=f"{interaction.user.mention} confirmed",
                color=0x00FF00
            ),
            ephemeral=True
        )
        
        if len(self.confirmed) == 2:
            await interaction.message.edit(view=None)
            if self.confirm_type == "roles":
                await ask_for_deal_amount(interaction.channel)
            elif self.confirm_type == "amount":
                await show_payment_invoice(interaction.channel)

    @ui.button(label="Cancel", style=ButtonStyle.red)
    async def cancel(self, interaction, button):
        deal = active_deals[self.channel_id]
        if interaction.user.id not in [deal['sender'].id, deal['receiver'].id]:
            return await interaction.response.send_message(
                "❌ Only deal participants can cancel!",
                ephemeral=True
            )
        
        await interaction.message.delete()
        if self.confirm_type == "roles":
            deal['sender'] = None
            deal['receiver'] = None
            await interaction.channel.send(
                embed=Embed(
                    title="Roles Reset",
                    description="Please select roles again",
                    color=0xFF0000
                ),
                view=RoleView(self.channel_id)
            )
        else:
            await ask_for_deal_amount(interaction.channel)

async def start_deal(channel):
    deal_code = generate_deal_code()
    await channel.send(
        f"{deal_code}\n\n"
        "Please send the Developer ID of the user you're dealing with.\n"
        "Type `cancel` to cancel the deal."
    )
    
    try:
        def check(m):
            return (
                m.channel == channel and 
                m.author != bot.user and
                (m.content.lower() == 'cancel' or m.content.strip().isdigit())
            )
        
        msg = await bot.wait_for('message', check=check, timeout=300)
        if msg.content.lower() == 'cancel':
            return await channel.delete()
        
        user_id = int(msg.content.strip())
        user = await bot.fetch_user(user_id)
        await channel.set_permissions(user, read_messages=True, send_messages=True)
        
        active_deals[channel.id] = {
            'stage': 'roles',
            'start_time': datetime.now(),
            'developer_id': user_id,
            'code': deal_code
        }
        
        await channel.send(
            embed=Embed(
                title="Role Selection",
                description="Please select your role:",
                color=0x5865F2
            ),
            view=RoleView(channel.id)
        )
        
    except (asyncio.TimeoutError, ValueError):
        await channel.delete()

async def ask_for_deal_amount(channel):
    deal = active_deals[channel.id]
    deal['stage'] = 'awaiting_amount'
    
    await channel.send(
        embed=Embed(
            title="Enter Amount (USD)",
            description="Minimum: $0.10\nExample: `1.50`",
            color=0x5865F2
        )
    )

    def check(m):
        amount = validate_amount(m.content)
        return (
            amount is not None and
            m.channel == channel and
            m.author == deal['sender']
        )

    try:
        msg = await bot.wait_for('message', check=check, timeout=300)
        usd_amount = float(msg.content.replace('$', '').strip())
        ltc_amount = usd_amount / get_live_rate()
        
        deal.update({
            'amount_usd': usd_amount,
            'amount_ltc': ltc_amount,
            'stage': 'amount_confirmation'
        })

        confirm_embed = Embed(
            title="Confirm Amount",
            description=f"${usd_amount:.2f} USD ≈ {ltc_amount:.8f} LTC",
            color=0x5865F2
        )
        await channel.send(
            embed=confirm_embed,
            view=ConfirmView("amount", channel.id)
        )
        
    except asyncio.TimeoutError:
        await channel.delete()

async def show_payment_invoice(channel):
    deal = active_deals[channel.id]
    
    class InvoiceView(ui.View):
        def __init__(self):
            super().__init__(timeout=None)
        
        @ui.button(label="Show Address", style=ButtonStyle.green)
        async def show_address(self, interaction, button):
            await interaction.response.send_message(
                f"Send exactly {deal['amount_ltc']:.8f} LTC to:\n`{get_ltc_address()}`",
                ephemeral=False
            )
        
        @ui.button(label="QR Code", style=ButtonStyle.blurple)
        async def qr_code(self, interaction, button):
            with open('qr.txt') as f:
                qr_url = f.read().strip()
            await interaction.response.send_message(
                f"Payment QR Code: {qr_url}",
                ephemeral=False
            )
    
    await channel.send(
        embed=Embed(
            title="PAYMENT INVOICE",
            description=(
                f"**Amount:** ${deal['amount_usd']:.2f} USD\n"
                f"**Converted:** {deal['amount_ltc']:.8f} LTC\n"
                f"**Rate:** 1 LTC = ${get_live_rate():.2f}"
            ),
            color=0x5865F2
        ),
        view=InvoiceView()
    )
    
    deal['stage'] = 'awaiting_payment'
    monitor_payment.start(channel)

@tasks.loop(seconds=30)
async def monitor_payment(channel):
    deal = active_deals[channel.id]
    payment = check_payment(get_ltc_address(), deal['amount_ltc'])
    
    if payment:
        await payment_tracker.update_status(channel, payment)
        monitor_payment.stop()
    elif (datetime.now() - deal['start_time']).total_seconds() > config['deal_timeout']:
        await channel.delete()
        monitor_payment.stop()

async def show_release_options(channel):
    deal = active_deals[channel.id]
    
    class ReleaseView(ui.View):
        def __init__(self):
            super().__init__(timeout=None)
        
        @ui.button(label="Release", style=ButtonStyle.green)
        async def release(self, interaction, button):
            if interaction.user != deal['sender']:
                return await interaction.response.send_message(
                    "❌ Only the sender can release funds!",
                    ephemeral=True
                )
            
            await interaction.response.send_modal(ReleaseModal())
    
    class ReleaseModal(ui.Modal):
        def __init__(self):
            super().__init__(title="Release Funds")
            self.address = ui.TextInput(
                label="Receiver LTC Address",
                placeholder="L...",
                min_length=26,
                max_length=48
            )
            self.add_item(self.address)
        
        async def on_submit(self, interaction):
            if not validate_ltc_address(self.address.value):
                return await interaction.response.send_message(
                    "❌ Invalid LTC address!",
                    ephemeral=True
                )
            
            txid = send_ltc(
                self.address.value,
                deal['amount_ltc'],
                get_wif_key()
            )
            
            await interaction.channel.send(
                embed=Embed(
                    title="✅ Funds Released",
                    description=(
                        f"**Amount:** {deal['amount_ltc']:.8f} LTC\n"
                        f"**To:** `{self.address.value}`\n"
                        f"**TXID:** `{txid}`"
                    ),
                    color=0x00FF00
                )
            )
            await interaction.response.defer()
    
    await channel.send(
        embed=Embed(
            title="Release Funds",
            description=f"✅ Payment confirmed! Amount: {deal['amount_ltc']:.8f} LTC",
            color=0x00FF00
        ),
        view=ReleaseView()
    )

@bot.command()
@commands.is_owner()
async def release(ctx, deal_id: str, ltc_address: str):
    """Owner override to release funds"""
    for channel_id, deal in active_deals.items():
        if deal['code'] == deal_id:
            if not validate_ltc_address(ltc_address):
                return await ctx.send("❌ Invalid LTC address!")
            
            txid = send_ltc(
                ltc_address,
                deal['amount_ltc'],
                get_wif_key()
            )
            
            channel = bot.get_channel(channel_id)
            await channel.send(
                embed=Embed(
                    title="💰 Funds Released (Owner)",
                    description=(
                        f"**Amount:** {deal['amount_ltc']:.8f} LTC\n"
                        f"**To:** `{ltc_address}`\n"
                        f"**TXID:** `{txid}`"
                    ),
                    color=0x00FF00
                )
            )
            return await ctx.send("✅ Funds released!")
    
    await ctx.send("❌ Deal not found!")

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    await bot.load_extension('cogs.rates')

bot.run(config['bot_token'])

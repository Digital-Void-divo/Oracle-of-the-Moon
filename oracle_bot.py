import discord
from discord import app_commands
from discord.ui import Button, View
import random
import os

# Bot setup
intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# GitHub repo settings for card images
GITHUB_USERNAME = "Digital-Void-divo"
GITHUB_REPO = "Oracle-of-the-Moon"
GITHUB_BRANCH = "main"
IMAGE_FOLDER = "card_images"

def get_card_image_url(card_name):
    """Generate GitHub raw URL for a card image"""
    # Convert card name to filename (lowercase, replace spaces with hyphens)
    filename = card_name.lower().replace(" ", "-").replace("•", "").strip()
    # Add .png extension
    filename = f"{filename}.png"
    return f"https://raw.githubusercontent.com/{GITHUB_USERNAME}/{GITHUB_REPO}/{GITHUB_BRANCH}/{IMAGE_FOLDER}/{filename}"

# Card deck - using a mix of playing cards and basic tarot for demo
CARDS = {
    # Major Arcana (simplified for demo)
    "The Fool": "New beginnings, innocence, spontaneity, free spirit",
    "The Magician": "Manifestation, resourcefulness, power, inspired action",
    "The High Priestess": "Intuition, sacred knowledge, divine feminine, subconscious",
    "The Empress": "Femininity, beauty, nature, abundance, nurturing",
    "The Emperor": "Authority, structure, control, fatherhood",
    "The Lovers": "Love, harmony, relationships, values alignment",
    "The Chariot": "Control, willpower, success, determination",
    "Strength": "Courage, inner strength, patience, compassion",
    "The Hermit": "Soul searching, introspection, inner guidance, solitude",
    "Wheel of Fortune": "Good luck, karma, life cycles, destiny",
    "Justice": "Fairness, truth, cause and effect, law",
    "The Hanged Man": "Pause, surrender, letting go, new perspective",
    "Death": "Endings, transformation, transition, letting go",
    "Temperance": "Balance, moderation, patience, purpose",
    "The Devil": "Shadow self, attachment, addiction, restriction",
    "The Tower": "Sudden change, upheaval, chaos, revelation",
    "The Star": "Hope, faith, purpose, renewal, spirituality",
    "The Moon": "Illusion, fear, anxiety, subconscious, intuition",
    "The Sun": "Positivity, fun, warmth, success, vitality",
    "Judgement": "Reflection, reckoning, inner calling, absolution",
    "The World": "Completion, accomplishment, travel, fulfillment",
}

# Deck state - tracks what's been drawn
deck_state = {}

def get_deck(guild_id):
    """Get or initialize deck for a guild"""
    if guild_id not in deck_state:
        deck_state[guild_id] = list(CARDS.keys())
        random.shuffle(deck_state[guild_id])
    return deck_state[guild_id]

def shuffle_deck(guild_id):
    """Reset and shuffle the deck"""
    deck_state[guild_id] = list(CARDS.keys())
    random.shuffle(deck_state[guild_id])

class CardRevealView(View):
    def __init__(self, cards, positions=None):
        super().__init__(timeout=300)  # 5 minute timeout
        self.cards = cards  # List of card names
        self.revealed = [False] * len(cards)
        self.positions = positions or [f"Card {i+1}" for i in range(len(cards))]
        
        # Create a button for each card
        for i in range(len(cards)):
            button = Button(
                label=f"🎴 {self.positions[i]}",
                style=discord.ButtonStyle.primary,
                custom_id=f"card_{i}"
            )
            button.callback = self.make_callback(i)
            self.add_item(button)
    
    def make_callback(self, index):
        async def callback(interaction: discord.Interaction):
            if not self.revealed[index]:
                self.revealed[index] = True
                
                # Update button to show it's revealed
                for item in self.children:
                    if item.custom_id == f"card_{index}":
                        item.label = f"✨ {self.positions[index]}"
                        item.style = discord.ButtonStyle.success
                        item.disabled = True
                
                # Create embed for revealed card
                card_name = self.cards[index]
                card_meaning = CARDS[card_name]
                
                embed = discord.Embed(
                    title=f"🔮 {card_name}",
                    description=card_meaning,
                    color=discord.Color.purple()
                )
                
                # Add card image if available
                image_url = get_card_image_url(card_name)
                embed.set_image(url=image_url)
                
                embed.set_footer(text=self.positions[index])
                
                await interaction.response.edit_message(view=self)
                await interaction.followup.send(embed=embed, ephemeral=False)
            else:
                await interaction.response.send_message("This card has already been revealed! ✨", ephemeral=True)
        
        return callback

@tree.command(name="shuffle", description="Shuffle the deck for a fresh start")
async def shuffle(interaction: discord.Interaction):
    guild_id = interaction.guild_id or interaction.user.id
    shuffle_deck(guild_id)
    
    embed = discord.Embed(
        title="🔮 Deck Shuffled",
        description="The cards have been shuffled and reset. Ready for a new reading! ✨",
        color=discord.Color.purple()
    )
    await interaction.response.send_message(embed=embed)

@tree.command(name="draw", description="Draw cards from the deck")
@app_commands.describe(count="Number of cards to draw (1-5)")
async def draw(interaction: discord.Interaction, count: int = 1):
    if count < 1 or count > 5:
        await interaction.response.send_message("Please draw between 1 and 5 cards! 🎴", ephemeral=True)
        return
    
    guild_id = interaction.guild_id or interaction.user.id
    deck = get_deck(guild_id)
    
    # Check if we have enough cards
    if len(deck) < count:
        shuffle_deck(guild_id)
        deck = get_deck(guild_id)
        reshuffle_msg = "\n\n*The deck has been automatically reshuffled! 🔄*"
    else:
        reshuffle_msg = ""
    
    # Draw cards
    drawn_cards = [deck.pop(0) for _ in range(count)]
    
    # Create view with flip buttons
    view = CardRevealView(drawn_cards)
    
    embed = discord.Embed(
        title=f"🎴 {count} Card{'s' if count > 1 else ''} Drawn",
        description=f"Click the buttons below to reveal each card one at a time! ✨{reshuffle_msg}",
        color=discord.Color.blue()
    )
    
    # Add card back image
    card_back_url = f"https://raw.githubusercontent.com/{GITHUB_USERNAME}/{GITHUB_REPO}/{GITHUB_BRANCH}/{IMAGE_FOLDER}/card-back.png"
    embed.set_thumbnail(url=card_back_url)
    
    embed.set_footer(text=f"Cards remaining in deck: {len(deck)}")
    
    await interaction.response.send_message(embed=embed, view=view)

@tree.command(name="spread", description="Perform a card spread reading")
@app_commands.describe(spread_type="Type of spread to perform")
@app_commands.choices(spread_type=[
    app_commands.Choice(name="Past • Present • Future (3 cards)", value="past_present_future"),
    app_commands.Choice(name="Mind • Body • Spirit (3 cards)", value="mind_body_spirit"),
    app_commands.Choice(name="Situation • Action • Outcome (3 cards)", value="situation_action_outcome"),
])
async def spread(interaction: discord.Interaction, spread_type: str):
    guild_id = interaction.guild_id or interaction.user.id
    deck = get_deck(guild_id)
    
    # Define spread positions
    spreads = {
        "past_present_future": ["Past", "Present", "Future"],
        "mind_body_spirit": ["Mind", "Body", "Spirit"],
        "situation_action_outcome": ["Situation", "Action", "Outcome"],
    }
    
    positions = spreads[spread_type]
    card_count = len(positions)
    
    # Check if we have enough cards
    if len(deck) < card_count:
        shuffle_deck(guild_id)
        deck = get_deck(guild_id)
        reshuffle_msg = "\n\n*The deck has been automatically reshuffled! 🔄*"
    else:
        reshuffle_msg = ""
    
    # Draw cards for spread
    drawn_cards = [deck.pop(0) for _ in range(card_count)]
    
    # Create view with labeled buttons
    view = CardRevealView(drawn_cards, positions)
    
    spread_title = spread_type.replace("_", " • ").title()
    
    embed = discord.Embed(
        title=f"🔮 {spread_title} Spread",
        description=f"Your cards have been laid out. Click each position to reveal! ✨{reshuffle_msg}",
        color=discord.Color.purple()
    )
    
    # Add card back image
    card_back_url = f"https://raw.githubusercontent.com/{GITHUB_USERNAME}/{GITHUB_REPO}/{GITHUB_BRANCH}/{IMAGE_FOLDER}/card-back.png"
    embed.set_thumbnail(url=card_back_url)
    
    embed.set_footer(text=f"Cards remaining in deck: {len(deck)}")
    
    await interaction.response.send_message(embed=embed, view=view)

@tree.command(name="deck_info", description="See information about the current deck")
async def deck_info(interaction: discord.Interaction):
    guild_id = interaction.guild_id or interaction.user.id
    deck = get_deck(guild_id)
    
    embed = discord.Embed(
        title="🎴 Current Deck",
        description=f"**Demo Tarot Deck** (Major Arcana)\n\nA simplified tarot deck for demonstration. Your friend can customize this with her oracle cards!",
        color=discord.Color.gold()
    )
    embed.add_field(name="Total Cards", value=str(len(CARDS)), inline=True)
    embed.add_field(name="Remaining", value=str(len(deck)), inline=True)
    embed.add_field(name="Drawn", value=str(len(CARDS) - len(deck)), inline=True)
    
    await interaction.response.send_message(embed=embed)

@client.event
async def on_ready():
    await tree.sync()
    print(f'✅ Logged in as {client.user}')
    print(f'🔮 Oracle card bot ready!')
    print(f'📝 Commands: /shuffle, /draw, /spread, /deck_info')

# Run the bot
client.run(os.getenv('DISCORD_TOKEN'))

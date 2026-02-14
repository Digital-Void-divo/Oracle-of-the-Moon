import discord
from discord import app_commands
from discord.ui import Button, View
import random
import os
import io
from PIL import Image
import requests

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

def get_card_back_url():
    """Get the card back image URL"""
    return f"https://raw.githubusercontent.com/{GITHUB_USERNAME}/{GITHUB_REPO}/{GITHUB_BRANCH}/{IMAGE_FOLDER}/card-back.png"

# Image cache to avoid re-downloading
image_cache = {}

def download_card_image(url):
    """Download and cache a card image"""
    if url in image_cache:
        print(f"Using cached image for {url}")
        return image_cache[url]
    
    try:
        response = requests.get(url, timeout=10)
        print(f"Downloaded {url}: status={response.status_code}, content-type={response.headers.get('content-type')}, size={len(response.content)}")
        
        if response.status_code == 200:
            content_type = response.headers.get('content-type', '')
            if 'image' not in content_type:
                print(f"Warning: Content-Type is {content_type}, not an image!")
                print(f"First 100 bytes: {response.content[:100]}")
                return None
            
            img = Image.open(io.BytesIO(response.content))
            img.load()  # Force load to validate
            if img.mode != 'RGBA':
                img = img.convert('RGBA')
            
            # Cache the image
            image_cache[url] = img.copy()
            print(f"Cached image: {url}, size: {img.size}")
            return img
        else:
            print(f"Failed to download: status {response.status_code}")
            return None
    except Exception as e:
        print(f"Error downloading {url}: {e}")
        import traceback
        traceback.print_exc()
        return None

def create_composite_image(cards, revealed_indices):
    """Create a composite image showing cards side by side"""
    try:
        card_images = []
        card_back_url = get_card_back_url()
        
        print(f"Creating composite for {len(cards)} cards, revealed: {revealed_indices}")
        
        # Download and process each card
        for i, card_name in enumerate(cards):
            if i in revealed_indices:
                url = get_card_image_url(card_name)
                print(f"Card {i} ({card_name}): Getting face from {url}")
            else:
                url = card_back_url
                print(f"Card {i}: Getting card back")
            
            img = download_card_image(url)
            if img:
                card_images.append(img.copy())
            else:
                print(f"Failed to get image for card {i}")
                return None
        
        if not card_images:
            print("No card images loaded!")
            return None
        
        # Calculate dimensions for composite
        card_width, card_height = card_images[0].size
        spacing = 20  # pixels between cards
        total_width = (card_width * len(card_images)) + (spacing * (len(card_images) - 1))
        total_height = card_height
        
        print(f"Creating composite: {total_width}x{total_height}")
        
        # Create composite image
        composite = Image.new('RGBA', (total_width, total_height), (0, 0, 0, 0))
        
        # Paste each card
        x_offset = 0
        for idx, img in enumerate(card_images):
            composite.paste(img, (x_offset, 0))
            x_offset += card_width + spacing
        
        # Convert to bytes for Discord
        img_bytes = io.BytesIO()
        composite.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        
        print(f"Composite created successfully! Size: {img_bytes.getbuffer().nbytes} bytes")
        return img_bytes
    except Exception as e:
        print(f"Error creating composite image: {e}")
        import traceback
        traceback.print_exc()
        return None

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
    def __init__(self, cards, positions, interaction, reversed_cards):
        super().__init__(timeout=300)  # 5 minute timeout
        self.cards = cards  # List of card names
        self.reversed_cards = reversed_cards  # List of bools indicating if card is reversed
        self.revealed = set()  # Set of revealed indices
        self.positions = positions or [f"Card {i+1}" for i in range(len(cards))]
        self.interaction = interaction
        self.message = None
        
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
            if index not in self.revealed:
                self.revealed.add(index)
                
                # Update button to show it's revealed
                for item in self.children:
                    if item.custom_id == f"card_{index}":
                        item.label = f"✨ {self.positions[index]}"
                        item.style = discord.ButtonStyle.success
                        item.disabled = True
                
                # Just show the revealed card in a new message
                card_name = self.cards[index]
                is_reversed = self.reversed_cards[index]
                card_meaning = CARDS[card_name]
                
                # Get the card face image
                card_url = get_card_image_url(card_name)
                
                # Add reversed indicator
                title = f"🔮 {self.positions[index]}: {card_name}"
                if is_reversed:
                    title += " (Reversed)"
                    # Add reversed meaning context
                    card_meaning = f"🔄 **Reversed**\n\n{card_meaning}\n\n*When reversed, this card's energy is blocked, internalized, or expressing in shadow form. Consider the opposite or inverse of the upright meaning.*"
                
                embed = discord.Embed(
                    title=title,
                    description=card_meaning,
                    color=discord.Color.purple() if not is_reversed else discord.Color.blue()
                )
                embed.set_image(url=card_url)
                
                # Update the view on the original message
                await interaction.message.edit(view=self)
                
                # Send the revealed card as a new message
                await interaction.response.send_message(embed=embed)
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
    
    # Randomly determine which cards are reversed (50% chance each)
    reversed_cards = [random.choice([True, False]) for _ in range(count)]
    
    # Defer response since image generation might take a moment
    await interaction.response.defer()
    
    # Create initial composite with all cards face down
    composite_bytes = create_composite_image(drawn_cards, set())
    
    if composite_bytes:
        file = discord.File(composite_bytes, filename="cards.png")
        
        # Create view with flip buttons
        view = CardRevealView(drawn_cards, [f"Card {i+1}" for i in range(count)], interaction, reversed_cards)
        
        embed = discord.Embed(
            title=f"🎴 {count} Card{'s' if count > 1 else ''} Drawn",
            description=f"Click the buttons below to reveal each card! ✨{reshuffle_msg}",
            color=discord.Color.blue()
        )
        embed.set_image(url="attachment://cards.png")
        embed.set_footer(text=f"Cards remaining in deck: {len(deck)}")
        
        await interaction.followup.send(embed=embed, file=file, view=view)
    else:
        await interaction.followup.send("Failed to create card display. Please try again!", ephemeral=True)

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
    
    # Randomly determine which cards are reversed (50% chance each)
    reversed_cards = [random.choice([True, False]) for _ in range(card_count)]
    
    # Defer response since image generation might take a moment
    await interaction.response.defer()
    
    # Create initial composite with all cards face down
    composite_bytes = create_composite_image(drawn_cards, set())
    
    if composite_bytes:
        file = discord.File(composite_bytes, filename="cards.png")
        
        # Create view with labeled buttons
        view = CardRevealView(drawn_cards, positions, interaction, reversed_cards)
        
        spread_title = spread_type.replace("_", " • ").title()
        
        embed = discord.Embed(
            title=f"🔮 {spread_title} Spread",
            description=f"Your cards have been laid out. Click each position to reveal! ✨{reshuffle_msg}",
            color=discord.Color.purple()
        )
        embed.set_image(url="attachment://cards.png")
        embed.set_footer(text=f"Cards remaining in deck: {len(deck)}")
        
        await interaction.followup.send(embed=embed, file=file, view=view)
    else:
        await interaction.followup.send("Failed to create card display. Please try again!", ephemeral=True)

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

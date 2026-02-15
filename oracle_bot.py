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

def download_card_image(url, rotate=False):
    """Download and cache a card image"""
    cache_key = f"{url}_rotated" if rotate else url
    
    if cache_key in image_cache:
        print(f"Using cached image for {cache_key}")
        return image_cache[cache_key]
    
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
            
            # Rotate 180 degrees if reversed
            if rotate:
                img = img.rotate(180, expand=True)
            
            # Cache the image
            image_cache[cache_key] = img.copy()
            print(f"Cached image: {cache_key}, size: {img.size}")
            return img
        else:
            print(f"Failed to download: status {response.status_code}")
            return None
    except Exception as e:
        print(f"Error downloading {url}: {e}")
        import traceback
        traceback.print_exc()
        return None

def create_composite_image(cards, revealed_indices, reversed_cards):
    """Create a composite image showing cards side by side"""
    try:
        card_images = []
        card_back_url = get_card_back_url()
        
        print(f"Creating composite for {len(cards)} cards, revealed: {revealed_indices}")
        
        # Download and process each card
        for i, card_name in enumerate(cards):
            if i in revealed_indices:
                url = get_card_image_url(card_name)
                is_reversed = reversed_cards[i]
                print(f"Card {i} ({card_name}): Getting face from {url}, reversed={is_reversed}")
                img = download_card_image(url, rotate=is_reversed)
            else:
                url = card_back_url
                print(f"Card {i}: Getting card back")
                img = download_card_image(url, rotate=False)
            
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
        
        # Resize images if composite would be too large
        # Discord has 8MB limit, so keep width reasonable
        max_width = 3000  # pixels
        if total_width > max_width:
            scale_factor = max_width / total_width
            card_width = int(card_width * scale_factor)
            card_height = int(card_height * scale_factor)
            spacing = int(spacing * scale_factor)
            total_width = (card_width * len(card_images)) + (spacing * (len(card_images) - 1))
            total_height = card_height
            
            # Resize all card images
            card_images = [img.resize((card_width, card_height), Image.Resampling.LANCZOS) for img in card_images]
            print(f"Resized cards to fit within {max_width}px width")
        
        print(f"Creating composite: {total_width}x{total_height}")
        
        # Create composite image
        composite = Image.new('RGBA', (total_width, total_height), (0, 0, 0, 0))
        
        # Paste each card
        x_offset = 0
        for idx, img in enumerate(card_images):
            composite.paste(img, (x_offset, 0))
            x_offset += card_width + spacing
        
        # Convert to bytes for Discord with optimization
        img_bytes = io.BytesIO()
        
        # Try PNG first with compression
        composite.save(img_bytes, format='PNG', optimize=True)
        file_size = img_bytes.getbuffer().nbytes
        
        # If still too large, convert to JPEG with quality reduction
        if file_size > 6_500_000:  # 6.5MB threshold (lower for edit safety)
            print(f"PNG too large ({file_size} bytes), converting to JPEG")
            img_bytes = io.BytesIO()
            # Convert to RGB for JPEG (no transparency)
            rgb_composite = Image.new('RGB', composite.size, (20, 20, 30))  # Dark background
            rgb_composite.paste(composite, mask=composite.split()[3] if composite.mode == 'RGBA' else None)
            rgb_composite.save(img_bytes, format='JPEG', quality=75, optimize=True)
            file_size = img_bytes.getbuffer().nbytes
            
            # If STILL too large, resize
            if file_size > 6_500_000:
                print(f"JPEG still too large ({file_size} bytes), resizing...")
                scale = 0.75
                new_size = (int(rgb_composite.width * scale), int(rgb_composite.height * scale))
                rgb_composite = rgb_composite.resize(new_size, Image.Resampling.LANCZOS)
                img_bytes = io.BytesIO()
                rgb_composite.save(img_bytes, format='JPEG', quality=75, optimize=True)
                file_size = img_bytes.getbuffer().nbytes
        
        img_bytes.seek(0)
        
        print(f"Composite created successfully! Size: {file_size} bytes ({file_size / 1_000_000:.2f}MB)")
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
                
                # Defer the response since we need time to generate image
                await interaction.response.defer()
                
                # Create new composite image with this card revealed
                composite_bytes = create_composite_image(self.cards, self.revealed, self.reversed_cards)
                
                if composite_bytes:
                    file = discord.File(composite_bytes, filename="cards.png")
                    
                    # Build description showing revealed card info
                    card_name = self.cards[index]
                    is_reversed = self.reversed_cards[index]
                    card_meaning = CARDS[card_name]
                    
                    # Create list of revealed cards
                    revealed_info = []
                    for i in sorted(self.revealed):
                        title = f"**{self.positions[i]}:** {self.cards[i]}"
                        if self.reversed_cards[i]:
                            title += " (Reversed)"
                        meaning = CARDS[self.cards[i]]
                        if self.reversed_cards[i]:
                            meaning = f"🔄 {meaning}\n*When reversed, this card's energy is blocked, internalized, or expressing in shadow form.*"
                        revealed_info.append(f"{title}\n*{meaning}*")
                    
                    description = "\n\n".join(revealed_info) if revealed_info else "Click a card to reveal!"
                    
                    embed = discord.Embed(
                        title=f"🔮 Card Reading",
                        description=description,
                        color=discord.Color.purple()
                    )
                    embed.set_image(url="attachment://cards.png")
                    embed.set_footer(text=f"{len(self.revealed)}/{len(self.cards)} cards revealed")
                    
                    # Edit the original message
                    await interaction.message.edit(embed=embed, view=self, attachments=[file])
                else:
                    await interaction.followup.send("Failed to load card image!", ephemeral=True)
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
    composite_bytes = create_composite_image(drawn_cards, set(), reversed_cards)
    
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

@tree.command(name="ask", description="Draw a card as an answer to your question")
@app_commands.describe(question="Your question for the cards")
async def ask(interaction: discord.Interaction, question: str):
    guild_id = interaction.guild_id or interaction.user.id
    deck = get_deck(guild_id)
    
    # Check if we have enough cards
    if len(deck) < 1:
        shuffle_deck(guild_id)
        deck = get_deck(guild_id)
        reshuffle_msg = "\n\n*The deck has been automatically reshuffled! 🔄*"
    else:
        reshuffle_msg = ""
    
    # Draw one card
    drawn_card = deck.pop(0)
    is_reversed = random.choice([True, False])
    
    # Defer response since image generation might take a moment
    await interaction.response.defer()
    
    # Create initial composite with card face down
    composite_bytes = create_composite_image([drawn_card], set(), [is_reversed])
    
    if composite_bytes:
        file = discord.File(composite_bytes, filename="cards.png")
        
        # Create view with flip button
        view = CardRevealView([drawn_card], ["Answer"], interaction, [is_reversed])
        
        # Truncate question if too long
        display_question = question if len(question) <= 200 else question[:197] + "..."
        
        embed = discord.Embed(
            title=f"❓ Question",
            description=f"*{display_question}*\n\nClick the button below to reveal your answer! ✨{reshuffle_msg}",
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
    composite_bytes = create_composite_image(drawn_cards, set(), reversed_cards)
    
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

@tree.command(name="custom_spread", description="Create your own custom card spread")
@app_commands.describe(
    name="Name for your spread (e.g., 'Self Discovery')",
    positions="Position names separated by commas (e.g., 'Past, Present, Future')"
)
async def custom_spread(interaction: discord.Interaction, name: str, positions: str):
    guild_id = interaction.guild_id or interaction.user.id
    deck = get_deck(guild_id)
    
    # Parse positions from comma-separated string
    position_list = [p.strip() for p in positions.split(",") if p.strip()]
    
    # Validate position count
    if len(position_list) < 1:
        await interaction.response.send_message("You need at least 1 position for a spread! 🎴", ephemeral=True)
        return
    
    if len(position_list) > 10:
        await interaction.response.send_message("Maximum 10 positions per spread! 🎴", ephemeral=True)
        return
    
    card_count = len(position_list)
    
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
    composite_bytes = create_composite_image(drawn_cards, set(), reversed_cards)
    
    if composite_bytes:
        file = discord.File(composite_bytes, filename="cards.png")
        
        # Create view with custom position labels
        view = CardRevealView(drawn_cards, position_list, interaction, reversed_cards)
        
        embed = discord.Embed(
            title=f"🔮 {name} Spread",
            description=f"Your custom spread has been laid out. Click each position to reveal! ✨{reshuffle_msg}\n\n**Positions:** {', '.join(position_list)}",
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

@tree.command(name="card_info", description="Look up a specific card's meaning")
@app_commands.describe(card_name="Name of the card to look up")
async def card_info(interaction: discord.Interaction, card_name: str):
    # Try to find the card (case-insensitive partial match)
    card_name_lower = card_name.lower()
    matches = [name for name in CARDS.keys() if card_name_lower in name.lower()]
    
    if not matches:
        await interaction.response.send_message(
            f"❌ Card '{card_name}' not found. Use `/deck_info` to see all available cards.",
            ephemeral=True
        )
        return
    
    if len(matches) > 1:
        # Multiple matches - show options
        match_list = "\n".join([f"• {name}" for name in matches[:10]])
        await interaction.response.send_message(
            f"🔍 Multiple cards match '{card_name}':\n{match_list}\n\nPlease be more specific!",
            ephemeral=True
        )
        return
    
    # Single match found
    found_card = matches[0]
    card_meaning = CARDS[found_card]
    card_url = get_card_image_url(found_card)
    
    embed = discord.Embed(
        title=f"🔮 {found_card}",
        description=f"**Upright Meaning:**\n{card_meaning}\n\n**Reversed Meaning:**\n🔄 When reversed, this card's energy is blocked, internalized, or expressing in shadow form. Consider the opposite or inverse of the upright meaning.",
        color=discord.Color.purple()
    )
    embed.set_image(url=card_url)
    embed.set_footer(text="This does not draw the card from the deck")
    
    await interaction.response.send_message(embed=embed)

@client.event
async def on_ready():
    await tree.sync()
    print(f'✅ Logged in as {client.user}')
    print(f'🔮 Oracle card bot ready!')
    print(f'📝 Commands: /shuffle, /draw, /ask, /spread, /custom_spread, /deck_info, /card_info')

# Run the bot
client.run(os.getenv('DISCORD_TOKEN'))

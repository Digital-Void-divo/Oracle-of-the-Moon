import discord
from discord import app_commands
from discord.ui import Button, View
import random
import os
import io
from PIL import Image
import requests
import json
from datetime import datetime
import base64

# Bot setup
intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# GitHub repo settings for card images
GITHUB_USERNAME = "Digital-Void-divo"
GITHUB_REPO = "Oracle-of-the-Moon"
GITHUB_BRANCH = "main"
IMAGE_FOLDER = "card_images"
JOURNAL_FILE = "journals.json"

# GitHub token for writing journals (set in Railway environment variables)
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')

def get_journals_from_github():
    """Fetch the journals.json file from GitHub"""
    url = f"https://api.github.com/repos/{GITHUB_USERNAME}/{GITHUB_REPO}/contents/{JOURNAL_FILE}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"} if GITHUB_TOKEN else {}
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            content = base64.b64decode(response.json()['content']).decode('utf-8')
            return json.loads(content), response.json()['sha']
        elif response.status_code == 404:
            # File doesn't exist yet, return empty journal
            return [], None
        else:
            print(f"Error fetching journals: {response.status_code}")
            return [], None
    except Exception as e:
        print(f"Error loading journals: {e}")
        return [], None

def save_journals_to_github(journals, sha=None):
    """Save the journals.json file to GitHub"""
    if not GITHUB_TOKEN:
        print("ERROR: GITHUB_TOKEN not set! Cannot save journals.")
        return False
    
    url = f"https://api.github.com/repos/{GITHUB_USERNAME}/{GITHUB_REPO}/contents/{JOURNAL_FILE}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Content-Type": "application/json"
    }
    
    content = json.dumps(journals, indent=2)
    encoded_content = base64.b64encode(content.encode('utf-8')).decode('utf-8')
    
    data = {
        "message": f"Update journals - {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC",
        "content": encoded_content,
        "branch": GITHUB_BRANCH
    }
    
    if sha:
        data["sha"] = sha
    
    try:
        response = requests.put(url, headers=headers, json=data)
        if response.status_code in [200, 201]:
            print("Journals saved successfully to GitHub")
            return True
        else:
            print(f"Error saving journals: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"Error saving journals: {e}")
        return False

# Store last reading per user for journaling
last_readings = {}

# Track reading stats
reading_stats = {
    "total_readings": 0,
    "readings_by_date": {},  # {date: count}
    "readings_by_person": {},  # {user_id: count}
    "cards_drawn": {},  # {card_name: count}
    "last_reading_date": None
}

class JournalPaginationView(View):
    def __init__(self, entries, user_id, page=0, per_page=10):
        super().__init__(timeout=180)
        self.entries = entries
        self.user_id = user_id
        self.page = page
        self.per_page = per_page
        self.max_page = (len(entries) - 1) // per_page
        
        # Add previous button
        prev_button = Button(label="◀ Previous", style=discord.ButtonStyle.primary, disabled=(page == 0))
        prev_button.callback = self.previous_page
        self.add_item(prev_button)
        
        # Add next button
        next_button = Button(label="Next ▶", style=discord.ButtonStyle.primary, disabled=(page >= self.max_page))
        next_button.callback = self.next_page
        self.add_item(next_button)
    
    async def previous_page(self, interaction: discord.Interaction):
        if interaction.user.id != int(self.user_id):
            await interaction.response.send_message("This isn't your journal!", ephemeral=True)
            return
        
        self.page -= 1
        await self.update_message(interaction)
    
    async def next_page(self, interaction: discord.Interaction):
        if interaction.user.id != int(self.user_id):
            await interaction.response.send_message("This isn't your journal!", ephemeral=True)
            return
        
        self.page += 1
        await self.update_message(interaction)
    
    async def update_message(self, interaction: discord.Interaction):
        start = self.page * self.per_page
        end = start + self.per_page
        page_entries = self.entries[start:end]
        
        entries_list = "\n".join([
            f"• **{j['name']}** - {datetime.fromisoformat(j['timestamp']).strftime('%b %d, %Y')}"
            for j in page_entries
        ])
        
        embed = discord.Embed(
            title=f"📖 Your Journal ({len(self.entries)} entries)",
            description=f"{entries_list}\n\nUse `/journal_view [name]` to view a specific entry.",
            color=discord.Color.blue()
        )
        embed.set_footer(text=f"Page {self.page + 1} of {self.max_page + 1}")
        
        # Update buttons
        for item in self.children:
            if item.label == "◀ Previous":
                item.disabled = (self.page == 0)
            elif item.label == "Next ▶":
                item.disabled = (self.page >= self.max_page)
        
        await interaction.response.edit_message(embed=embed, view=self)

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
undo_state = {}  # Tracks last drawn cards for undo functionality

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
    # Clear undo state when shuffling
    if guild_id in undo_state:
        del undo_state[guild_id]

def save_undo_state(guild_id, cards):
    """Save cards for potential undo"""
    undo_state[guild_id] = cards

def can_undo(guild_id):
    """Check if undo is available"""
    return guild_id in undo_state and len(undo_state[guild_id]) > 0

def undo_draw(guild_id):
    """Undo the last draw and return cards to deck"""
    if not can_undo(guild_id):
        return []
    
    cards = undo_state[guild_id]
    deck = get_deck(guild_id)
    
    # Add cards back to the front of the deck
    for card in reversed(cards):
        deck.insert(0, card)
    
    # Clear undo state
    del undo_state[guild_id]
    
    return cards

def save_last_reading(user_id, reading_data):
    """Save the last reading for potential journaling"""
    last_readings[user_id] = reading_data

def track_reading(cards, for_user_id=None):
    """Track stats for a completed reading"""
    today = datetime.utcnow().date().isoformat()
    
    # Increment total
    reading_stats["total_readings"] += 1
    
    # Track by date
    if today not in reading_stats["readings_by_date"]:
        reading_stats["readings_by_date"][today] = 0
    reading_stats["readings_by_date"][today] += 1
    
    # Track by person (for_user_id is the person reading was for)
    person_key = str(for_user_id) if for_user_id else "personal"
    if person_key not in reading_stats["readings_by_person"]:
        reading_stats["readings_by_person"][person_key] = 0
    reading_stats["readings_by_person"][person_key] += 1
    
    # Track cards drawn
    for card in cards:
        if card not in reading_stats["cards_drawn"]:
            reading_stats["cards_drawn"][card] = 0
        reading_stats["cards_drawn"][card] += 1
    
    # Update last reading date
    reading_stats["last_reading_date"] = today

class CardRevealView(View):
    def __init__(self, cards, positions, interaction, reversed_cards, question=None, reading_type="draw", for_user=None):
        super().__init__(timeout=300)  # 5 minute timeout
        self.cards = cards  # List of card names
        self.reversed_cards = reversed_cards  # List of bools indicating if card is reversed
        self.revealed = set()  # Set of revealed indices
        self.positions = positions or [f"Card {i+1}" for i in range(len(cards))]
        self.interaction = interaction
        self.message = None
        self.question = question  # Optional question for /ask command
        self.reading_type = reading_type  # Type of reading (draw, ask, spread, custom_spread, clarifier)
        self.for_user = for_user  # User this reading is for (None = personal)
        
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
                    
                    # Prepend question if this is from /ask command
                    if self.question:
                        description = f"❓ **Question:** *{self.question}*\n\n" + description
                    
                    embed = discord.Embed(
                        title=f"🔮 Card Reading",
                        description=description,
                        color=discord.Color.purple()
                    )
                    embed.set_image(url="attachment://cards.png")
                    embed.set_footer(text=f"{len(self.revealed)}/{len(self.cards)} cards revealed")
                    
                    # Edit the original message
                    await interaction.message.edit(embed=embed, view=self, attachments=[file])
                    
                    # Save reading for journaling when all cards are revealed
                    if len(self.revealed) == len(self.cards):
                        reading_data = {
                            "timestamp": datetime.utcnow().isoformat(),
                            "reading_type": self.reading_type,
                            "question": self.question,
                            "for_user": self.for_user,
                            "cards": [
                                {
                                    "name": self.cards[i],
                                    "position": self.positions[i],
                                    "reversed": self.reversed_cards[i]
                                }
                                for i in range(len(self.cards))
                            ]
                        }
                        save_last_reading(interaction.user.id, reading_data)
                        
                        # Track stats
                        track_reading(self.cards, for_user_id=self.for_user)
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
    
    # Save for undo
    save_undo_state(guild_id, drawn_cards)
    
    # Randomly determine which cards are reversed (50% chance each)
    reversed_cards = [random.choice([True, False]) for _ in range(count)]
    
    # Defer response since image generation might take a moment
    await interaction.response.defer()
    
    # Create initial composite with all cards face down
    composite_bytes = create_composite_image(drawn_cards, set(), reversed_cards)
    
    if composite_bytes:
        file = discord.File(composite_bytes, filename="cards.png")
        
        # Create view with flip buttons
        view = CardRevealView(drawn_cards, [f"Card {i+1}" for i in range(count)], interaction, reversed_cards, reading_type="draw")
        
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
    
    # Save for undo
    save_undo_state(guild_id, [drawn_card])
    
    is_reversed = random.choice([True, False])
    
    # Defer response since image generation might take a moment
    await interaction.response.defer()
    
    # Create initial composite with card face down
    composite_bytes = create_composite_image([drawn_card], set(), [is_reversed])
    
    if composite_bytes:
        file = discord.File(composite_bytes, filename="cards.png")
        
        # Truncate question if too long
        display_question = question if len(question) <= 200 else question[:197] + "..."
        
        # Create view with flip button
        view = CardRevealView([drawn_card], ["Answer"], interaction, [is_reversed], question=display_question)
        
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
    
    # Save for undo
    save_undo_state(guild_id, drawn_cards)
    
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
    
    # Save for undo
    save_undo_state(guild_id, drawn_cards)
    
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

@tree.command(name="undo", description="Undo the last card draw and return cards to the deck")
async def undo(interaction: discord.Interaction):
    guild_id = interaction.guild_id or interaction.user.id
    
    if not can_undo(guild_id):
        await interaction.response.send_message(
            "❌ No recent draw to undo! You can only undo the most recent draw.",
            ephemeral=True
        )
        return
    
    cards = undo_draw(guild_id)
    card_list = ", ".join(cards)
    
    embed = discord.Embed(
        title="↩️ Draw Undone",
        description=f"Returned {len(cards)} card{'s' if len(cards) > 1 else ''} to the deck:\n*{card_list}*",
        color=discord.Color.green()
    )
    embed.set_footer(text="These cards have been placed back at the top of the deck")
    
    await interaction.response.send_message(embed=embed)

@tree.command(name="undo_and_shuffle", description="Undo the last draw, return cards, and shuffle the remaining deck")
async def undo_and_shuffle(interaction: discord.Interaction):
    guild_id = interaction.guild_id or interaction.user.id
    
    if not can_undo(guild_id):
        await interaction.response.send_message(
            "❌ No recent draw to undo! You can only undo the most recent draw.",
            ephemeral=True
        )
        return
    
    cards = undo_draw(guild_id)
    card_list = ", ".join(cards)
    
    # Shuffle the deck (which now includes the returned cards)
    deck = get_deck(guild_id)
    random.shuffle(deck)
    
    embed = discord.Embed(
        title="↩️🔀 Undone & Shuffled",
        description=f"Returned {len(cards)} card{'s' if len(cards) > 1 else ''} to the deck:\n*{card_list}*\n\nThe entire deck has been shuffled! ✨",
        color=discord.Color.green()
    )
    embed.set_footer(text=f"{len(deck)} cards in deck")
    
    await interaction.response.send_message(embed=embed)

@tree.command(name="pull_clarifier", description="Draw an additional card to clarify a previous reading")
async def pull_clarifier(interaction: discord.Interaction):
    guild_id = interaction.guild_id or interaction.user.id
    deck = get_deck(guild_id)
    
    # Check if we have enough cards
    if len(deck) < 1:
        shuffle_deck(guild_id)
        deck = get_deck(guild_id)
        reshuffle_msg = "\n\n*The deck has been automatically reshuffled! 🔄*"
    else:
        reshuffle_msg = ""
    
    # Draw one clarifier card
    drawn_card = deck.pop(0)
    
    # Clarifiers are added to existing undo state, not replacing it
    # This way you can undo the whole reading including clarifier
    if can_undo(guild_id):
        undo_state[guild_id].append(drawn_card)
    else:
        save_undo_state(guild_id, [drawn_card])
    
    is_reversed = random.choice([True, False])
    
    # Defer response since image generation might take a moment
    await interaction.response.defer()
    
    # Create initial composite with card face down
    composite_bytes = create_composite_image([drawn_card], set(), [is_reversed])
    
    if composite_bytes:
        file = discord.File(composite_bytes, filename="cards.png")
        
        # Create view with flip button
        view = CardRevealView([drawn_card], ["Clarifier"], interaction, [is_reversed])
        
        embed = discord.Embed(
            title=f"🔍 Clarifier Card",
            description=f"An additional card drawn to provide clarity or deeper insight.{reshuffle_msg}",
            color=discord.Color.gold()
        )
        embed.set_image(url="attachment://cards.png")
        embed.set_footer(text=f"Cards remaining in deck: {len(deck)}")
        
        await interaction.followup.send(embed=embed, file=file, view=view)
    else:
        await interaction.followup.send("Failed to create card display. Please try again!", ephemeral=True)

@tree.command(name="reading_for", description="Perform a reading for another person")
@app_commands.describe(
    user="The person this reading is for",
    reading_type="Type of reading to perform"
)
@app_commands.choices(reading_type=[
    app_commands.Choice(name="Draw Cards", value="draw"),
    app_commands.Choice(name="Ask a Question", value="ask"),
    app_commands.Choice(name="Past • Present • Future", value="past_present_future"),
    app_commands.Choice(name="Mind • Body • Spirit", value="mind_body_spirit"),
    app_commands.Choice(name="Situation • Action • Outcome", value="situation_action_outcome"),
])
async def reading_for(interaction: discord.Interaction, user: discord.User, reading_type: str):
    guild_id = interaction.guild_id or interaction.user.id
    deck = get_deck(guild_id)
    
    # Determine card count and positions based on reading type
    if reading_type == "draw":
        card_count = 3  # Default to 3 cards for "draw"
        positions = [f"Card {i+1}" for i in range(card_count)]
        title = f"🎴 Reading for {user.mention}"
        color = discord.Color.blue()
    elif reading_type == "ask":
        card_count = 1
        positions = ["Answer"]
        title = f"❓ Question Reading for {user.mention}"
        color = discord.Color.blue()
    else:
        # It's a spread
        spreads = {
            "past_present_future": ["Past", "Present", "Future"],
            "mind_body_spirit": ["Mind", "Body", "Spirit"],
            "situation_action_outcome": ["Situation", "Action", "Outcome"],
        }
        positions = spreads[reading_type]
        card_count = len(positions)
        spread_title = reading_type.replace("_", " • ").title()
        title = f"🔮 {spread_title} Spread for {user.mention}"
        color = discord.Color.purple()
    
    # Check if we have enough cards
    if len(deck) < card_count:
        shuffle_deck(guild_id)
        deck = get_deck(guild_id)
        reshuffle_msg = "\n\n*The deck has been automatically reshuffled! 🔄*"
    else:
        reshuffle_msg = ""
    
    # Draw cards
    drawn_cards = [deck.pop(0) for _ in range(card_count)]
    
    # Save for undo
    save_undo_state(guild_id, drawn_cards)
    
    # Randomly determine which cards are reversed
    reversed_cards = [random.choice([True, False]) for _ in range(card_count)]
    
    # Defer response
    await interaction.response.defer()
    
    # Create initial composite with all cards face down
    composite_bytes = create_composite_image(drawn_cards, set(), reversed_cards)
    
    if composite_bytes:
        file = discord.File(composite_bytes, filename="cards.png")
        
        # Create view with flip buttons
        view = CardRevealView(drawn_cards, positions, interaction, reversed_cards, reading_type=reading_type, for_user=user.id)
        
        embed = discord.Embed(
            title=title,
            description=f"Click the buttons below to reveal each card! ✨{reshuffle_msg}",
            color=color
        )
        embed.set_image(url="attachment://cards.png")
        embed.set_footer(text=f"Reading by {interaction.user.display_name} • Cards remaining: {len(deck)}")
        
        await interaction.followup.send(embed=embed, file=file, view=view)
    else:
        await interaction.followup.send("Failed to create card display. Please try again!", ephemeral=True)

@tree.command(name="journal", description="Save your last reading to your personal journal")
@app_commands.describe(
    name="A unique name for this reading (e.g., 'Career Decision', 'Morning Reflection')",
    notes="Your personal notes or reflections on the reading"
)
async def journal(interaction: discord.Interaction, name: str, notes: str):
    user_id = interaction.user.id
    
    # Check if there's a recent reading to save
    if user_id not in last_readings:
        await interaction.response.send_message(
            "❌ No recent reading to journal! Complete a reading first (cards must be fully revealed).",
            ephemeral=True
        )
        return
    
    await interaction.response.defer(ephemeral=True)
    
    # Get journals from GitHub
    journals, sha = get_journals_from_github()
    
    # Check if name already exists for this user
    user_id_str = str(user_id)
    existing = next((j for j in journals if j.get("user_id") == user_id_str and j.get("name").lower() == name.lower()), None)
    
    if existing:
        await interaction.followup.send(
            f"❌ You already have a journal entry named '{name}'! Use a different name or delete the old one first with `/journal_delete {name}`",
            ephemeral=True
        )
        return
    
    # Create journal entry
    reading = last_readings[user_id]
    entry = {
        "user_id": user_id_str,
        "name": name,
        "timestamp": reading["timestamp"],
        "reading_type": reading["reading_type"],
        "question": reading["question"],
        "for_user": reading.get("for_user"),  # User ID this reading was for
        "cards": reading["cards"],
        "notes": notes
    }
    
    journals.append(entry)
    
    # Save to GitHub
    if save_journals_to_github(journals, sha):
        # Format cards for display
        cards_display = "\n".join([
            f"• **{card['position']}:** {card['name']}{' (Reversed)' if card['reversed'] else ''}"
            for card in reading["cards"]
        ])
        
        # Add "Reading for" if applicable
        for_user_text = ""
        if reading.get("for_user"):
            try:
                user_obj = await interaction.client.fetch_user(int(reading["for_user"]))
                for_user_text = f"**Reading for:** {user_obj.name}\n\n"
            except:
                for_user_text = f"**Reading for:** User ID {reading['for_user']}\n\n"
        
        embed = discord.Embed(
            title="📝 Reading Journaled",
            description=f"**Name:** {name}\n\n{for_user_text}**Your Notes:**\n{notes}\n\n**Cards:**\n{cards_display}",
            color=discord.Color.green()
        )
        embed.set_footer(text=f"Saved • {datetime.fromisoformat(reading['timestamp']).strftime('%B %d, %Y at %I:%M %p')} UTC")
        
        await interaction.followup.send(embed=embed, ephemeral=True)
    else:
        await interaction.followup.send(
            "❌ Failed to save journal entry. Make sure GITHUB_TOKEN is set in Railway!",
            ephemeral=True
        )

@tree.command(name="journal_view", description="View your journal entries")
@app_commands.describe(name="Optional: View a specific entry by name")
async def journal_view(interaction: discord.Interaction, name: str = None):
    user_id = str(interaction.user.id)
    
    await interaction.response.defer(ephemeral=True)
    
    # Get journals from GitHub
    journals, _ = get_journals_from_github()
    
    # Filter to this user's entries
    user_journals = [j for j in journals if j.get("user_id") == user_id]
    
    if not user_journals:
        await interaction.followup.send(
            "📖 Your journal is empty! Use `/journal [name] [notes]` after a reading to save it.",
            ephemeral=True
        )
        return
    
    if name:
        # View specific entry by name
        entry = next((j for j in user_journals if j.get("name").lower() == name.lower()), None)
        if not entry:
            await interaction.followup.send(
                f"❌ Entry '{name}' not found in your journal!",
                ephemeral=True
            )
            return
        
        cards_display = "\n".join([
            f"• **{card['position']}:** {card['name']}{' (Reversed)' if card['reversed'] else ''}"
            for card in entry["cards"]
        ])
        
        question_text = f"**Question:** *{entry['question']}*\n\n" if entry.get("question") else ""
        
        embed = discord.Embed(
            title=f"📖 {entry['name']}",
            description=f"{question_text}**Cards:**\n{cards_display}\n\n**Your Notes:**\n{entry['notes']}",
            color=discord.Color.purple()
        )
        embed.add_field(name="Reading Type", value=entry['reading_type'].replace('_', ' ').title(), inline=True)
        embed.add_field(name="Date", value=datetime.fromisoformat(entry['timestamp']).strftime('%B %d, %Y'), inline=True)
        
        await interaction.followup.send(embed=embed, ephemeral=True)
    else:
        # List all entries with pagination
        sorted_entries = sorted(user_journals, key=lambda x: x['timestamp'], reverse=True)
        
        if len(sorted_entries) <= 10:
            # No pagination needed
            entries_list = "\n".join([
                f"• **{j['name']}** - {datetime.fromisoformat(j['timestamp']).strftime('%b %d, %Y')}"
                for j in sorted_entries
            ])
            
            embed = discord.Embed(
                title=f"📖 Your Journal ({len(user_journals)} entries)",
                description=f"{entries_list}\n\nUse `/journal_view [name]` to view a specific entry.",
                color=discord.Color.blue()
            )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            # Use pagination
            page_entries = sorted_entries[:10]
            entries_list = "\n".join([
                f"• **{j['name']}** - {datetime.fromisoformat(j['timestamp']).strftime('%b %d, %Y')}"
                for j in page_entries
            ])
            
            embed = discord.Embed(
                title=f"📖 Your Journal ({len(user_journals)} entries)",
                description=f"{entries_list}\n\nUse `/journal_view [name]` to view a specific entry.",
                color=discord.Color.blue()
            )
            embed.set_footer(text=f"Page 1 of {(len(sorted_entries) - 1) // 10 + 1}")
            
            view = JournalPaginationView(sorted_entries, user_id, page=0, per_page=10)
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)

@tree.command(name="journal_delete", description="Delete a journal entry")
@app_commands.describe(name="The name of the entry to delete")
async def journal_delete(interaction: discord.Interaction, name: str):
    user_id = str(interaction.user.id)
    
    await interaction.response.defer(ephemeral=True)
    
    # Get journals from GitHub
    journals, sha = get_journals_from_github()
    
    # Find the entry
    entry = next((j for j in journals if j.get("name").lower() == name.lower() and j.get("user_id") == user_id), None)
    
    if not entry:
        await interaction.followup.send(
            f"❌ Entry '{name}' not found in your journal!",
            ephemeral=True
        )
        return
    
    # Remove it
    journals = [j for j in journals if not (j.get("name").lower() == name.lower() and j.get("user_id") == user_id)]
    
    # Save to GitHub
    if save_journals_to_github(journals, sha):
        await interaction.followup.send(
            f"🗑️ Entry '{name}' deleted from your journal.",
            ephemeral=True
        )
    else:
        await interaction.followup.send(
            "❌ Failed to delete entry. Please try again.",
            ephemeral=True
        )

@tree.command(name="reading_stats", description="View statistics about your readings")
async def reading_stats_command(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    
    stats = reading_stats
    
    if stats["total_readings"] == 0:
        await interaction.followup.send(
            "📊 No readings yet! Complete a reading to start tracking stats.",
            ephemeral=True
        )
        return
    
    # Calculate streak
    today = datetime.utcnow().date()
    streak = 0
    check_date = today
    while check_date.isoformat() in stats["readings_by_date"]:
        streak += 1
        check_date = check_date.replace(day=check_date.day - 1) if check_date.day > 1 else check_date.replace(month=check_date.month - 1, day=28)
    
    # Most active day of week
    day_counts = {}
    for date_str, count in stats["readings_by_date"].items():
        date_obj = datetime.fromisoformat(date_str)
        day_name = date_obj.strftime("%A")
        if day_name not in day_counts:
            day_counts[day_name] = 0
        day_counts[day_name] += count
    
    most_active_day = max(day_counts.items(), key=lambda x: x[1]) if day_counts else ("N/A", 0)
    
    # Readings per person
    person_list = []
    for person_id, count in sorted(stats["readings_by_person"].items(), key=lambda x: x[1], reverse=True)[:5]:
        if person_id == "personal":
            person_list.append(f"• Personal: {count} readings")
        else:
            try:
                user_obj = await interaction.client.fetch_user(int(person_id))
                person_list.append(f"• {user_obj.name}: {count} readings")
            except:
                person_list.append(f"• User {person_id}: {count} readings")
    
    person_text = "\n".join(person_list) if person_list else "No readings yet"
    
    # Most and least drawn cards
    if stats["cards_drawn"]:
        most_drawn = max(stats["cards_drawn"].items(), key=lambda x: x[1])
        least_drawn = min(stats["cards_drawn"].items(), key=lambda x: x[1])
        
        # Find cards never drawn
        all_cards = set(CARDS.keys())
        drawn_cards = set(stats["cards_drawn"].keys())
        never_drawn = all_cards - drawn_cards
        
        if never_drawn:
            least_drawn = (list(never_drawn)[0], 0)
        
        cards_text = f"**Most Drawn:** {most_drawn[0]} ({most_drawn[1]} times)\n**Least Drawn:** {least_drawn[0]} ({least_drawn[1]} times)"
    else:
        cards_text = "No card data yet"
    
    embed = discord.Embed(
        title="📊 Reading Statistics",
        color=discord.Color.gold()
    )
    embed.add_field(name="📈 Total Readings", value=str(stats["total_readings"]), inline=True)
    embed.add_field(name="🔥 Current Streak", value=f"{streak} day{'s' if streak != 1 else ''}", inline=True)
    embed.add_field(name="⭐ Most Active Day", value=f"{most_active_day[0]} ({most_active_day[1]} readings)", inline=True)
    embed.add_field(name="👥 Readings Per Person", value=person_text, inline=False)
    embed.add_field(name="🎴 Card Stats", value=cards_text, inline=False)
    
    await interaction.followup.send(embed=embed, ephemeral=True)

@client.event
async def on_ready():
    await tree.sync()
    print(f'✅ Logged in as {client.user}')
    print(f'🔮 Oracle card bot ready!')
    print(f'📝 Commands: /shuffle, /draw, /ask, /spread, /custom_spread, /reading_for, /pull_clarifier, /undo, /undo_and_shuffle, /deck_info, /card_info, /journal, /journal_view, /journal_delete, /reading_stats')

# Run the bot
client.run(os.getenv('DISCORD_TOKEN'))

import discord
from discord import app_commands
from discord.ui import Button, View
import random
import os
import io
from PIL import Image, ImageDraw
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
DECKS_FILE = "decks.json"

GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')

active_decks = {}
loaded_decks = {}

def load_decks_from_github():
    url = f"https://api.github.com/repos/{GITHUB_USERNAME}/{GITHUB_REPO}/contents/{DECKS_FILE}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"} if GITHUB_TOKEN else {}
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            content = base64.b64decode(response.json()['content']).decode('utf-8')
            decks_data = json.loads(content)
            loaded_decks.update(decks_data)
            print(f"Loaded {len(decks_data)} decks from GitHub")
            return True
        elif response.status_code == 404:
            print("No decks.json found, using default deck")
            loaded_decks["Demo Tarot"] = {"cards": CARDS, "image_folder": "tarot"}
            return False
        else:
            print(f"Error loading decks: {response.status_code}")
            loaded_decks["Demo Tarot"] = {"cards": CARDS, "image_folder": "tarot"}
            return False
    except Exception as e:
        print(f"Error loading decks: {e}")
        loaded_decks["Demo Tarot"] = {"cards": CARDS, "image_folder": "tarot"}
        return False

def get_active_deck(guild_id):
    if guild_id not in active_decks:
        active_decks[guild_id] = list(loaded_decks.keys())[0] if loaded_decks else "Demo Tarot"
    return active_decks[guild_id]

def get_deck_cards(guild_id):
    deck_name = get_active_deck(guild_id)
    if deck_name in loaded_decks:
        return loaded_decks[deck_name]["cards"]
    return CARDS

def get_deck_image_folder(guild_id):
    deck_name = get_active_deck(guild_id)
    if deck_name in loaded_decks:
        return loaded_decks[deck_name].get("image_folder", "tarot")
    return "tarot"

def get_card_meaning(card_name, guild_id):
    """Get a card's meaning from the active deck"""
    cards = get_deck_cards(guild_id)
    return cards.get(card_name, "Card meaning not found")

def get_journals_from_github():
    url = f"https://api.github.com/repos/{GITHUB_USERNAME}/{GITHUB_REPO}/contents/{JOURNAL_FILE}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"} if GITHUB_TOKEN else {}
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            content = base64.b64decode(response.json()['content']).decode('utf-8')
            return json.loads(content), response.json()['sha']
        elif response.status_code == 404:
            return [], None
        else:
            print(f"Error fetching journals: {response.status_code}")
            return [], None
    except Exception as e:
        print(f"Error loading journals: {e}")
        return [], None

def save_journals_to_github(journals, sha=None):
    if not GITHUB_TOKEN:
        print("ERROR: GITHUB_TOKEN not set!")
        return False
    url = f"https://api.github.com/repos/{GITHUB_USERNAME}/{GITHUB_REPO}/contents/{JOURNAL_FILE}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Content-Type": "application/json"}
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

last_readings = {}

reading_stats = {
    "total_readings": 0,
    "readings_by_date": {},
    "readings_by_person": {},
    "cards_drawn": {},
    "last_reading_date": None
}

def check_emergent_draw(guild_id):
    """
    Simulates cards slipping out during a shuffle.
      - 0.25%  → Manifested Draw: 2 cards slip out.
      - 1.25%  → Emergent Draw:   1 card slips out.
    Returns (list_of_lost_cards, draw_type_string) or ([], None).
    """
    deck = get_deck(guild_id)
    roll = random.random()

    if roll < 0.0025:
        if len(deck) >= 2:
            lost = [deck.pop(random.randint(0, len(deck) - 1))]
            lost.append(deck.pop(random.randint(0, len(deck) - 1)))
            print(f"Manifested Draw triggered! Cards: {lost}")
            return lost, "Manifested Draw"
    elif roll < 0.015:
        if len(deck) >= 1:
            lost = [deck.pop(random.randint(0, len(deck) - 1))]
            print(f"Emergent Draw triggered! Card: {lost}")
            return lost, "Emergent Draw"

    return [], None

async def send_emergent_draw_message(interaction, lost_cards, draw_type, guild_id):
    """
    Sends a separate follow-up message displaying the slipped card(s)
    face-up, styled like a reading but labeled as Emergent or Manifested.
    Uses the active deck for card meanings.
    """
    if not lost_cards or draw_type is None:
        return

    cards = get_deck_cards(guild_id)
    reversed_cards = [random.choice([True, False]) for _ in lost_cards]
    revealed_indices = set(range(len(lost_cards)))

    composite_bytes = create_composite_image(lost_cards, revealed_indices, reversed_cards, guild_id)

    if draw_type == "Emergent Draw":
        title = "✦ Emergent Draw"
        flavor = (
            "*A card slipped free during the shuffle — tumbling loose before "
            "it could be returned to the fold. It has been removed from the deck.*"
        )
        color = discord.Color.teal()
    else:
        title = "✦ Manifested Draw"
        flavor = (
            "*The shuffle was restless. Two cards slipped free of their own accord — "
            "falling from the deck before the cards had settled. "
            "Both have been removed from the deck.*"
        )
        color = discord.Color.dark_purple()

    revealed_info = []
    for i, card_name in enumerate(lost_cards):
        line = f"**{card_name}**"
        if reversed_cards[i]:
            line += " (Reversed)"
        meaning = cards.get(card_name, "")
        if reversed_cards[i]:
            meaning = f"🔄 {meaning}\n*When reversed, this card's energy is blocked, internalized, or expressing in shadow form.*"
        revealed_info.append(f"{line}\n*{meaning}*")

    description = f"{flavor}\n\n" + "\n\n".join(revealed_info)

    embed = discord.Embed(title=title, description=description, color=color)

    if composite_bytes:
        embed.set_image(url="attachment://emergent.png")
        file = discord.File(composite_bytes, filename="emergent.png")
        await interaction.followup.send(embed=embed, file=file)
    else:
        await interaction.followup.send(embed=embed)

class JournalPaginationView(View):
    def __init__(self, entries, user_id, page=0, per_page=10):
        super().__init__(timeout=180)
        self.entries = entries
        self.user_id = user_id
        self.page = page
        self.per_page = per_page
        self.max_page = (len(entries) - 1) // per_page

        prev_button = Button(label="◀ Previous", style=discord.ButtonStyle.primary, disabled=(page == 0))
        prev_button.callback = self.previous_page
        self.add_item(prev_button)

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

        for item in self.children:
            if item.label == "◀ Previous":
                item.disabled = (self.page == 0)
            elif item.label == "Next ▶":
                item.disabled = (self.page >= self.max_page)

        await interaction.response.edit_message(embed=embed, view=self)

class DailyCardModal(discord.ui.Modal, title="Daily Card Interpretation"):
    note = discord.ui.TextInput(
        label="Your Interpretation",
        style=discord.TextStyle.paragraph,
        placeholder="Share your insight on today's card...",
        required=True,
        max_length=1000
    )

    def __init__(self, card_name, is_reversed, channel, guild_id):
        super().__init__()
        self.card_name = card_name
        self.is_reversed = is_reversed
        self.channel = channel
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        card_url = get_card_image_url(self.card_name, self.guild_id)
        cards = get_deck_cards(self.guild_id)
        card_meaning = cards.get(self.card_name, "")
        today = datetime.utcnow().strftime("%B %d, %Y")

        if self.is_reversed:
            title_card = f"{self.card_name} (Reversed)"
            meaning_text = f"🔄 {card_meaning}\n\n*When reversed, this card's energy is blocked, internalized, or expressing in shadow form.*"
        else:
            title_card = self.card_name
            meaning_text = card_meaning

        embed = discord.Embed(
            title=f"🌅 Daily Card - {today}",
            description=f"**{title_card}**\n\n*{meaning_text}*\n\n**Interpretation:**\n{self.note.value}",
            color=discord.Color.gold()
        )
        embed.set_image(url=card_url)
        embed.set_footer(text=f"Reading by {interaction.user.display_name}")

        try:
            await self.channel.send(embed=embed)
            await interaction.followup.send("✅ Daily card posted successfully!", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to post: {e}", ephemeral=True)

class DailyCardView(View):
    def __init__(self, card_name, is_reversed, channel, guild_id):
        super().__init__(timeout=300)
        self.card_name = card_name
        self.is_reversed = is_reversed
        self.channel = channel
        self.guild_id = guild_id

        button = Button(label="📝 Add Interpretation & Post", style=discord.ButtonStyle.green)
        button.callback = self.show_modal
        self.add_item(button)

    async def show_modal(self, interaction: discord.Interaction):
        modal = DailyCardModal(self.card_name, self.is_reversed, self.channel, self.guild_id)
        await interaction.response.send_modal(modal)

def get_card_image_url(card_name, guild_id=None):
    filename = card_name.lower().replace(" ", "-").replace("•", "").strip()
    filename = f"{filename}.png"
    if guild_id:
        deck_folder = get_deck_image_folder(guild_id)
    else:
        deck_folder = "tarot"
    return f"https://raw.githubusercontent.com/{GITHUB_USERNAME}/{GITHUB_REPO}/{GITHUB_BRANCH}/{IMAGE_FOLDER}/{deck_folder}/{filename}"

def get_card_back_url(guild_id=None):
    if guild_id:
        deck_folder = get_deck_image_folder(guild_id)
    else:
        deck_folder = "tarot"
    return f"https://raw.githubusercontent.com/{GITHUB_USERNAME}/{GITHUB_REPO}/{GITHUB_BRANCH}/{IMAGE_FOLDER}/{deck_folder}/card-back.png"

image_cache = {}

def create_fallback_card_back(width=200, height=350):
    img = Image.new('RGBA', (width, height), (30, 10, 60, 255))
    draw = ImageDraw.Draw(img)
    draw.rectangle([5, 5, width - 6, height - 6], outline=(180, 130, 255, 255), width=3)
    draw.rectangle([12, 12, width - 13, height - 13], outline=(120, 80, 200, 255), width=1)
    cx, cy = width // 2, height // 2
    draw.ellipse([cx - 30, cy - 30, cx + 30, cy + 30], outline=(200, 160, 255, 255), width=2)
    draw.ellipse([cx - 10, cy - 30, cx + 50, cy + 30], fill=(30, 10, 60, 255))
    return img

def download_card_image(url, rotate=False):
    cache_key = f"{url}_rotated" if rotate else url
    if cache_key in image_cache:
        return image_cache[cache_key]
    try:
        response = requests.get(url, timeout=10)
        print(f"Downloaded {url}: status={response.status_code}, size={len(response.content)}")
        if response.status_code == 200:
            content_type = response.headers.get('content-type', '')
            if 'image' not in content_type:
                if 'card-back' in url:
                    img = create_fallback_card_back()
                    image_cache[cache_key] = img.copy()
                    return img
                return None
            img = Image.open(io.BytesIO(response.content))
            img.load()
            if img.mode != 'RGBA':
                img = img.convert('RGBA')
            if rotate:
                img = img.rotate(180, expand=True)
            image_cache[cache_key] = img.copy()
            return img
        else:
            if 'card-back' in url:
                img = create_fallback_card_back()
                if rotate:
                    img = img.rotate(180, expand=True)
                image_cache[cache_key] = img.copy()
                return img
            return None
    except Exception as e:
        print(f"Error downloading {url}: {e}")
        import traceback
        traceback.print_exc()
        return None

def create_composite_image(cards, revealed_indices, reversed_cards, guild_id=None):
    try:
        card_images = []
        card_back_url = get_card_back_url(guild_id)

        print(f"Creating composite for {len(cards)} cards, revealed: {revealed_indices}")

        for i, card_name in enumerate(cards):
            if i in revealed_indices:
                url = get_card_image_url(card_name, guild_id)
                is_reversed = reversed_cards[i]
                img = download_card_image(url, rotate=is_reversed)
            else:
                img = download_card_image(card_back_url, rotate=False)

            if img:
                card_images.append(img.copy())
            else:
                print(f"Failed to get image for card {i}")
                return None

        if not card_images:
            return None

        card_width, card_height = card_images[0].size
        spacing = 20
        total_width = (card_width * len(card_images)) + (spacing * (len(card_images) - 1))
        total_height = card_height

        max_width = 3000
        if total_width > max_width:
            scale_factor = max_width / total_width
            card_width = int(card_width * scale_factor)
            card_height = int(card_height * scale_factor)
            spacing = int(spacing * scale_factor)
            total_width = (card_width * len(card_images)) + (spacing * (len(card_images) - 1))
            total_height = card_height
            card_images = [img.resize((card_width, card_height), Image.Resampling.LANCZOS) for img in card_images]

        composite = Image.new('RGBA', (total_width, total_height), (0, 0, 0, 0))
        x_offset = 0
        for img in card_images:
            composite.paste(img, (x_offset, 0))
            x_offset += card_width + spacing

        img_bytes = io.BytesIO()
        composite.save(img_bytes, format='PNG', optimize=True)
        file_size = img_bytes.getbuffer().nbytes

        if file_size > 6_500_000:
            img_bytes = io.BytesIO()
            rgb_composite = Image.new('RGB', composite.size, (20, 20, 30))
            rgb_composite.paste(composite, mask=composite.split()[3] if composite.mode == 'RGBA' else None)
            rgb_composite.save(img_bytes, format='JPEG', quality=75, optimize=True)
            file_size = img_bytes.getbuffer().nbytes

            if file_size > 6_500_000:
                scale = 0.75
                new_size = (int(rgb_composite.width * scale), int(rgb_composite.height * scale))
                rgb_composite = rgb_composite.resize(new_size, Image.Resampling.LANCZOS)
                img_bytes = io.BytesIO()
                rgb_composite.save(img_bytes, format='JPEG', quality=75, optimize=True)

        img_bytes.seek(0)
        print(f"Composite created: {img_bytes.getbuffer().nbytes / 1_000_000:.2f}MB")
        return img_bytes
    except Exception as e:
        print(f"Error creating composite image: {e}")
        import traceback
        traceback.print_exc()
        return None

# Default card deck (used only as fallback if decks.json is missing)
CARDS = {
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

deck_state = {}
undo_state = {}

def get_deck(guild_id):
    if guild_id not in deck_state:
        cards = get_deck_cards(guild_id)
        deck_state[guild_id] = list(cards.keys())
        random.shuffle(deck_state[guild_id])
    return deck_state[guild_id]

def shuffle_deck(guild_id):
    """Full reset — rebuilds the deck from scratch and shuffles"""
    cards = get_deck_cards(guild_id)
    deck_state[guild_id] = list(cards.keys())
    random.shuffle(deck_state[guild_id])
    if guild_id in undo_state:
        del undo_state[guild_id]

def shuffle_remaining(guild_id):
    """Shuffles only the cards currently in the deck, leaving drawn cards out"""
    deck = get_deck(guild_id)
    random.shuffle(deck)

def save_undo_state(guild_id, cards):
    undo_state[guild_id] = cards

def can_undo(guild_id):
    return guild_id in undo_state and len(undo_state[guild_id]) > 0

def undo_draw(guild_id):
    if not can_undo(guild_id):
        return []
    cards = undo_state[guild_id]
    deck = get_deck(guild_id)
    for card in reversed(cards):
        deck.insert(0, card)
    del undo_state[guild_id]
    return cards

def save_last_reading(user_id, reading_data):
    last_readings[user_id] = reading_data

def track_reading(cards, for_user_id=None):
    today = datetime.utcnow().date().isoformat()
    reading_stats["total_readings"] += 1
    if today not in reading_stats["readings_by_date"]:
        reading_stats["readings_by_date"][today] = 0
    reading_stats["readings_by_date"][today] += 1
    person_key = str(for_user_id) if for_user_id else "personal"
    if person_key not in reading_stats["readings_by_person"]:
        reading_stats["readings_by_person"][person_key] = 0
    reading_stats["readings_by_person"][person_key] += 1
    for card in cards:
        if card not in reading_stats["cards_drawn"]:
            reading_stats["cards_drawn"][card] = 0
        reading_stats["cards_drawn"][card] += 1
    reading_stats["last_reading_date"] = today

class CardRevealView(View):
    def __init__(self, cards, positions, interaction, reversed_cards, guild_id, question=None, reading_type="draw", for_user=None):
        super().__init__(timeout=300)
        self.cards = cards
        self.reversed_cards = reversed_cards
        self.revealed = set()
        self.positions = positions or [f"Card {i+1}" for i in range(len(cards))]
        self.interaction = interaction
        self.message = None
        self.question = question
        self.reading_type = reading_type
        self.for_user = for_user
        self.guild_id = guild_id  # Store so we can pull meanings from the active deck

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

                for item in self.children:
                    if item.custom_id == f"card_{index}":
                        item.label = f"✨ {self.positions[index]}"
                        item.style = discord.ButtonStyle.success
                        item.disabled = True

                await interaction.response.defer()

                composite_bytes = create_composite_image(self.cards, self.revealed, self.reversed_cards, self.guild_id)

                if composite_bytes:
                    file = discord.File(composite_bytes, filename="cards.png")

                    # Pull meanings from the active deck, not the hardcoded fallback
                    active_cards = get_deck_cards(self.guild_id)

                    revealed_info = []
                    for i in sorted(self.revealed):
                        title = f"**{self.positions[i]}:** {self.cards[i]}"
                        if self.reversed_cards[i]:
                            title += " (Reversed)"
                        meaning = active_cards.get(self.cards[i], "")
                        if self.reversed_cards[i]:
                            meaning = f"🔄 {meaning}\n*When reversed, this card's energy is blocked, internalized, or expressing in shadow form.*"
                        revealed_info.append(f"{title}\n*{meaning}*")

                    description = "\n\n".join(revealed_info) if revealed_info else "Click a card to reveal!"

                    if self.question:
                        description = f"❓ **Question:** *{self.question}*\n\n" + description

                    embed = discord.Embed(
                        title="🔮 Card Reading",
                        description=description,
                        color=discord.Color.purple()
                    )
                    embed.set_image(url="attachment://cards.png")
                    embed.set_footer(text=f"{len(self.revealed)}/{len(self.cards)} cards revealed")

                    await interaction.message.edit(embed=embed, view=self, attachments=[file])

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
                        track_reading(self.cards, for_user_id=self.for_user)
                else:
                    await interaction.followup.send("Failed to load card image!", ephemeral=True)
            else:
                await interaction.response.send_message("This card has already been revealed! ✨", ephemeral=True)

        return callback

@tree.command(name="shuffle", description="Fully reset and shuffle the deck")
async def shuffle(interaction: discord.Interaction):
    guild_id = interaction.guild_id or interaction.user.id
    shuffle_deck(guild_id)
    deck = get_deck(guild_id)

    await interaction.response.defer()

    lost_cards, draw_type = check_emergent_draw(guild_id)

    deck_name = get_active_deck(guild_id)
    embed = discord.Embed(
        title="🔮 Deck Shuffled",
        description=f"**{deck_name}** has been fully reset and shuffled. Ready for a new reading! ✨",
        color=discord.Color.purple()
    )
    embed.set_footer(text=f"Cards in deck: {len(deck)}")
    await interaction.followup.send(embed=embed)

    if lost_cards:
        await send_emergent_draw_message(interaction, lost_cards, draw_type, guild_id)

@tree.command(name="shuffle_remaining", description="Shuffle only the cards still in the deck, keeping drawn cards out")
async def shuffle_remaining_cmd(interaction: discord.Interaction):
    guild_id = interaction.guild_id or interaction.user.id
    deck = get_deck(guild_id)

    if len(deck) == 0:
        await interaction.response.send_message(
            "❌ No cards remain in the deck to shuffle! Use `/shuffle` to reset the full deck.",
            ephemeral=True
        )
        return

    cards_before = len(deck)
    shuffle_remaining(guild_id)

    await interaction.response.defer()

    lost_cards, draw_type = check_emergent_draw(guild_id)

    deck_name = get_active_deck(guild_id)
    total_cards = len(get_deck_cards(guild_id))
    drawn_count = total_cards - cards_before

    embed = discord.Embed(
        title="🔀 Remaining Cards Shuffled",
        description=(
            f"The remaining cards in **{deck_name}** have been shuffled.\n\n"
            f"*{drawn_count} card{'s' if drawn_count != 1 else ''} remain{'s' if drawn_count == 1 else ''} "
            f"out of the deck from previous draws.*"
        ),
        color=discord.Color.blurple()
    )
    embed.set_footer(text=f"Cards in deck: {len(deck)} / {total_cards}")
    await interaction.followup.send(embed=embed)

    if lost_cards:
        await send_emergent_draw_message(interaction, lost_cards, draw_type, guild_id)

@tree.command(name="draw", description="Draw cards from the deck")
@app_commands.describe(count="Number of cards to draw (1-5)")
async def draw(interaction: discord.Interaction, count: int = 1):
    if count < 1 or count > 5:
        await interaction.response.send_message("Please draw between 1 and 5 cards! 🎴", ephemeral=True)
        return

    guild_id = interaction.guild_id or interaction.user.id
    deck = get_deck(guild_id)

    if len(deck) < count:
        shuffle_deck(guild_id)
        deck = get_deck(guild_id)
        reshuffle_msg = "\n\n*The deck has been automatically reshuffled! 🔄*"
    else:
        reshuffle_msg = ""

    drawn_cards = [deck.pop(0) for _ in range(count)]
    save_undo_state(guild_id, drawn_cards)
    reversed_cards = [random.choice([True, False]) for _ in range(count)]

    await interaction.response.defer()

    composite_bytes = create_composite_image(drawn_cards, set(), reversed_cards, guild_id)

    if composite_bytes:
        file = discord.File(composite_bytes, filename="cards.png")
        view = CardRevealView(drawn_cards, [f"Card {i+1}" for i in range(count)], interaction, reversed_cards, guild_id, reading_type="draw")

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

    if len(deck) < 1:
        shuffle_deck(guild_id)
        deck = get_deck(guild_id)
        reshuffle_msg = "\n\n*The deck has been automatically reshuffled! 🔄*"
    else:
        reshuffle_msg = ""

    drawn_card = deck.pop(0)
    save_undo_state(guild_id, [drawn_card])
    is_reversed = random.choice([True, False])

    await interaction.response.defer()

    composite_bytes = create_composite_image([drawn_card], set(), [is_reversed], guild_id)

    if composite_bytes:
        file = discord.File(composite_bytes, filename="cards.png")
        display_question = question if len(question) <= 200 else question[:197] + "..."
        view = CardRevealView([drawn_card], ["Answer"], interaction, [is_reversed], guild_id, question=display_question)

        embed = discord.Embed(
            title="❓ Question",
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

    spreads = {
        "past_present_future": ["Past", "Present", "Future"],
        "mind_body_spirit": ["Mind", "Body", "Spirit"],
        "situation_action_outcome": ["Situation", "Action", "Outcome"],
    }

    positions = spreads[spread_type]
    card_count = len(positions)

    if len(deck) < card_count:
        shuffle_deck(guild_id)
        deck = get_deck(guild_id)
        reshuffle_msg = "\n\n*The deck has been automatically reshuffled! 🔄*"
    else:
        reshuffle_msg = ""

    drawn_cards = [deck.pop(0) for _ in range(card_count)]
    save_undo_state(guild_id, drawn_cards)
    reversed_cards = [random.choice([True, False]) for _ in range(card_count)]

    await interaction.response.defer()

    composite_bytes = create_composite_image(drawn_cards, set(), reversed_cards, guild_id)

    if composite_bytes:
        file = discord.File(composite_bytes, filename="cards.png")
        view = CardRevealView(drawn_cards, positions, interaction, reversed_cards, guild_id)
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

    position_list = [p.strip() for p in positions.split(",") if p.strip()]

    if len(position_list) < 1:
        await interaction.response.send_message("You need at least 1 position for a spread! 🎴", ephemeral=True)
        return

    if len(position_list) > 10:
        await interaction.response.send_message("Maximum 10 positions per spread! 🎴", ephemeral=True)
        return

    card_count = len(position_list)

    if len(deck) < card_count:
        shuffle_deck(guild_id)
        deck = get_deck(guild_id)
        reshuffle_msg = "\n\n*The deck has been automatically reshuffled! 🔄*"
    else:
        reshuffle_msg = ""

    drawn_cards = [deck.pop(0) for _ in range(card_count)]
    save_undo_state(guild_id, drawn_cards)
    reversed_cards = [random.choice([True, False]) for _ in range(card_count)]

    await interaction.response.defer()

    composite_bytes = create_composite_image(drawn_cards, set(), reversed_cards, guild_id)

    if composite_bytes:
        file = discord.File(composite_bytes, filename="cards.png")
        view = CardRevealView(drawn_cards, position_list, interaction, reversed_cards, guild_id)

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
    deck_name = get_active_deck(guild_id)
    total_cards = len(get_deck_cards(guild_id))

    embed = discord.Embed(
        title="🎴 Current Deck",
        description=f"**{deck_name}**",
        color=discord.Color.gold()
    )
    embed.add_field(name="Total Cards", value=str(total_cards), inline=True)
    embed.add_field(name="Remaining", value=str(len(deck)), inline=True)
    embed.add_field(name="Drawn", value=str(total_cards - len(deck)), inline=True)

    await interaction.response.send_message(embed=embed)

@tree.command(name="card_info", description="Look up a specific card's meaning")
@app_commands.describe(card_name="Name of the card to look up")
async def card_info(interaction: discord.Interaction, card_name: str):
    guild_id = interaction.guild_id or interaction.user.id
    active_cards = get_deck_cards(guild_id)
    card_name_lower = card_name.lower()
    matches = [name for name in active_cards.keys() if card_name_lower in name.lower()]

    if not matches:
        await interaction.response.send_message(
            f"❌ Card '{card_name}' not found in the current deck. Use `/deck_info` to check what deck is active.",
            ephemeral=True
        )
        return

    if len(matches) > 1:
        match_list = "\n".join([f"• {name}" for name in matches[:10]])
        await interaction.response.send_message(
            f"🔍 Multiple cards match '{card_name}':\n{match_list}\n\nPlease be more specific!",
            ephemeral=True
        )
        return

    found_card = matches[0]
    card_meaning = active_cards[found_card]
    card_url = get_card_image_url(found_card, guild_id)

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
    deck = get_deck(guild_id)
    random.shuffle(deck)

    await interaction.response.defer()

    lost_cards, draw_type = check_emergent_draw(guild_id)

    embed = discord.Embed(
        title="↩️🔀 Undone & Shuffled",
        description=f"Returned {len(cards)} card{'s' if len(cards) > 1 else ''} to the deck:\n*{card_list}*\n\nThe entire deck has been shuffled! ✨",
        color=discord.Color.green()
    )
    embed.set_footer(text=f"{len(deck)} cards in deck")
    await interaction.followup.send(embed=embed)

    if lost_cards:
        await send_emergent_draw_message(interaction, lost_cards, draw_type, guild_id)

@tree.command(name="pull_clarifier", description="Draw an additional card to clarify a previous reading")
async def pull_clarifier(interaction: discord.Interaction):
    guild_id = interaction.guild_id or interaction.user.id
    deck = get_deck(guild_id)

    if len(deck) < 1:
        shuffle_deck(guild_id)
        deck = get_deck(guild_id)
        reshuffle_msg = "\n\n*The deck has been automatically reshuffled! 🔄*"
    else:
        reshuffle_msg = ""

    drawn_card = deck.pop(0)

    if can_undo(guild_id):
        undo_state[guild_id].append(drawn_card)
    else:
        save_undo_state(guild_id, [drawn_card])

    is_reversed = random.choice([True, False])

    await interaction.response.defer()

    composite_bytes = create_composite_image([drawn_card], set(), [is_reversed], guild_id)

    if composite_bytes:
        file = discord.File(composite_bytes, filename="cards.png")
        view = CardRevealView([drawn_card], ["Clarifier"], interaction, [is_reversed], guild_id)

        embed = discord.Embed(
            title="🔍 Clarifier Card",
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

    if reading_type == "draw":
        card_count = 3
        positions = [f"Card {i+1}" for i in range(card_count)]
        title = f"🎴 Reading for {user.display_name}"
        color = discord.Color.blue()
    elif reading_type == "ask":
        card_count = 1
        positions = ["Answer"]
        title = f"❓ Question Reading for {user.display_name}"
        color = discord.Color.blue()
    else:
        spreads = {
            "past_present_future": ["Past", "Present", "Future"],
            "mind_body_spirit": ["Mind", "Body", "Spirit"],
            "situation_action_outcome": ["Situation", "Action", "Outcome"],
        }
        positions = spreads[reading_type]
        card_count = len(positions)
        spread_title = reading_type.replace("_", " • ").title()
        title = f"🔮 {spread_title} Spread for {user.display_name}"
        color = discord.Color.purple()

    if len(deck) < card_count:
        shuffle_deck(guild_id)
        deck = get_deck(guild_id)
        reshuffle_msg = "\n\n*The deck has been automatically reshuffled! 🔄*"
    else:
        reshuffle_msg = ""

    drawn_cards = [deck.pop(0) for _ in range(card_count)]
    save_undo_state(guild_id, drawn_cards)
    reversed_cards = [random.choice([True, False]) for _ in range(card_count)]

    await interaction.response.defer()

    composite_bytes = create_composite_image(drawn_cards, set(), reversed_cards, guild_id)

    if composite_bytes:
        file = discord.File(composite_bytes, filename="cards.png")
        view = CardRevealView(drawn_cards, positions, interaction, reversed_cards, guild_id, reading_type=reading_type, for_user=user.id)

        embed = discord.Embed(
            title=title,
            description=f"{user.mention} — Click the buttons below to reveal each card! ✨{reshuffle_msg}",
            color=color
        )
        embed.set_image(url="attachment://cards.png")
        embed.set_footer(text=f"Reading by {interaction.user.display_name} • Cards remaining: {len(deck)}")

        await interaction.followup.send(
            content=f"🔮 Reading for {user.mention}",
            embed=embed,
            file=file,
            view=view,
            allowed_mentions=discord.AllowedMentions(users=True)
        )
    else:
        await interaction.followup.send("Failed to create card display. Please try again!", ephemeral=True)

@tree.command(name="journal", description="Save your last reading to your personal journal")
@app_commands.describe(
    name="A unique name for this reading (e.g., 'Career Decision', 'Morning Reflection')",
    notes="Your personal notes or reflections on the reading"
)
async def journal(interaction: discord.Interaction, name: str, notes: str):
    user_id = interaction.user.id

    if user_id not in last_readings:
        await interaction.response.send_message(
            "❌ No recent reading to journal! Complete a reading first (cards must be fully revealed).",
            ephemeral=True
        )
        return

    await interaction.response.defer(ephemeral=True)

    journals, sha = get_journals_from_github()
    user_id_str = str(user_id)
    existing = next((j for j in journals if j.get("user_id") == user_id_str and j.get("name").lower() == name.lower()), None)

    if existing:
        await interaction.followup.send(
            f"❌ You already have a journal entry named '{name}'! Use a different name or delete the old one first with `/journal_delete {name}`",
            ephemeral=True
        )
        return

    reading = last_readings[user_id]
    entry = {
        "user_id": user_id_str,
        "name": name,
        "timestamp": reading["timestamp"],
        "reading_type": reading["reading_type"],
        "question": reading["question"],
        "for_user": reading.get("for_user"),
        "cards": reading["cards"],
        "notes": notes
    }

    journals.append(entry)

    if save_journals_to_github(journals, sha):
        cards_display = "\n".join([
            f"• **{card['position']}:** {card['name']}{' (Reversed)' if card['reversed'] else ''}"
            for card in reading["cards"]
        ])

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

    journals, _ = get_journals_from_github()
    user_journals = [j for j in journals if j.get("user_id") == user_id]

    if not user_journals:
        await interaction.followup.send(
            "📖 Your journal is empty! Use `/journal [name] [notes]` after a reading to save it.",
            ephemeral=True
        )
        return

    if name:
        entry = next((j for j in user_journals if j.get("name").lower() == name.lower()), None)
        if not entry:
            await interaction.followup.send(f"❌ Entry '{name}' not found in your journal!", ephemeral=True)
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
        sorted_entries = sorted(user_journals, key=lambda x: x['timestamp'], reverse=True)

        if len(sorted_entries) <= 10:
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

    journals, sha = get_journals_from_github()
    entry = next((j for j in journals if j.get("name").lower() == name.lower() and j.get("user_id") == user_id), None)

    if not entry:
        await interaction.followup.send(f"❌ Entry '{name}' not found in your journal!", ephemeral=True)
        return

    journals = [j for j in journals if not (j.get("name").lower() == name.lower() and j.get("user_id") == user_id)]

    if save_journals_to_github(journals, sha):
        await interaction.followup.send(f"🗑️ Entry '{name}' deleted from your journal.", ephemeral=True)
    else:
        await interaction.followup.send("❌ Failed to delete entry. Please try again.", ephemeral=True)

@tree.command(name="deck_list", description="View all available decks")
async def deck_list(interaction: discord.Interaction):
    guild_id = interaction.guild_id or interaction.user.id
    current_deck = get_active_deck(guild_id)

    if not loaded_decks:
        await interaction.response.send_message("❌ No decks available! Make sure decks.json is configured.", ephemeral=True)
        return

    deck_list_text = []
    for deck_name, deck_data in loaded_decks.items():
        card_count = len(deck_data["cards"])
        is_active = "✨ " if deck_name == current_deck else ""
        deck_list_text.append(f"{is_active}**{deck_name}** - {card_count} cards")

    embed = discord.Embed(
        title="🎴 Available Decks",
        description="\n".join(deck_list_text) + "\n\nUse `/deck_switch [deck_name]` to change decks.",
        color=discord.Color.blue()
    )
    embed.set_footer(text=f"Currently using: {current_deck}")

    await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="deck_switch", description="Switch to a different deck")
@app_commands.describe(deck_name="The name of the deck to switch to")
async def deck_switch(interaction: discord.Interaction, deck_name: str):
    guild_id = interaction.guild_id or interaction.user.id

    deck_match = None
    for name in loaded_decks.keys():
        if name.lower() == deck_name.lower():
            deck_match = name
            break

    if not deck_match:
        available = ", ".join(loaded_decks.keys())
        await interaction.response.send_message(
            f"❌ Deck '{deck_name}' not found!\n\nAvailable decks: {available}",
            ephemeral=True
        )
        return

    active_decks[guild_id] = deck_match
    shuffle_deck(guild_id)
    card_count = len(loaded_decks[deck_match]["cards"])

    embed = discord.Embed(
        title="🎴 Deck Switched",
        description=f"Now using **{deck_match}** ({card_count} cards)\n\nThe deck has been shuffled and is ready for readings! ✨",
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed)

@tree.command(name="daily_card", description="Draw and post a daily card to a channel")
@app_commands.describe(channel="The channel to post the daily card to")
async def daily_card(interaction: discord.Interaction, channel: discord.TextChannel):
    guild_id = interaction.guild_id or interaction.user.id
    deck = get_deck(guild_id)

    if len(deck) < 1:
        shuffle_deck(guild_id)
        deck = get_deck(guild_id)

    drawn_card = deck.pop(0)
    is_reversed = random.choice([True, False])
    active_cards = get_deck_cards(guild_id)
    card_meaning = active_cards.get(drawn_card, "")
    card_url = get_card_image_url(drawn_card, guild_id)

    title = f"{drawn_card}{' (Reversed)' if is_reversed else ''}"
    if is_reversed:
        meaning_text = f"🔄 {card_meaning}\n\n*When reversed, this card's energy is blocked, internalized, or expressing in shadow form.*"
    else:
        meaning_text = card_meaning

    embed = discord.Embed(
        title="🌅 Today's Daily Card",
        description=f"**{title}**\n\n*{meaning_text}*\n\nClick the button below to add your interpretation and post this to {channel.mention}!",
        color=discord.Color.gold()
    )
    embed.set_image(url=card_url)
    embed.set_footer(text="Only you can see this message")

    view = DailyCardView(drawn_card, is_reversed, channel, guild_id)
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

@tree.command(name="request_reading", description="Request a reading from the reader")
@app_commands.describe(topic="Optional: What you'd like guidance on")
async def request_reading(interaction: discord.Interaction, topic: str = None):
    guild = interaction.guild
    if not guild:
        await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
        return

    reader_role = discord.utils.get(guild.roles, name="Wasteland Oracle")

    if reader_role:
        readers = [member for member in guild.members if reader_role in member.roles]
        if readers:
            reader_mentions = " ".join([reader.mention for reader in readers])
        else:
            reader_mentions = reader_role.mention
    else:
        reader_mentions = "**Wasteland Oracle**"

    topic_text = f"\n**Topic:** {topic}" if topic else ""

    embed = discord.Embed(
        title="🔮 Reading Request",
        description=f"{reader_mentions}\n\n{interaction.user.mention} has requested a reading!{topic_text}",
        color=discord.Color.blue()
    )
    embed.set_footer(text=f"Requested by {interaction.user.display_name}")

    await interaction.response.send_message(
        embed=embed,
        allowed_mentions=discord.AllowedMentions(roles=True, users=True)
    )

@tree.command(name="reading_stats", description="View statistics about your readings")
async def reading_stats_command(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    stats = reading_stats

    if stats["total_readings"] == 0:
        await interaction.followup.send("📊 No readings yet! Complete a reading to start tracking stats.", ephemeral=True)
        return

    today = datetime.utcnow().date()
    streak = 0
    check_date = today
    while check_date.isoformat() in stats["readings_by_date"]:
        streak += 1
        check_date = check_date.replace(day=check_date.day - 1) if check_date.day > 1 else check_date.replace(month=check_date.month - 1, day=28)

    day_counts = {}
    for date_str, count in stats["readings_by_date"].items():
        date_obj = datetime.fromisoformat(date_str)
        day_name = date_obj.strftime("%A")
        if day_name not in day_counts:
            day_counts[day_name] = 0
        day_counts[day_name] += count

    most_active_day = max(day_counts.items(), key=lambda x: x[1]) if day_counts else ("N/A", 0)

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

    guild_id = interaction.guild_id or interaction.user.id
    active_cards = get_deck_cards(guild_id)

    if stats["cards_drawn"]:
        most_drawn = max(stats["cards_drawn"].items(), key=lambda x: x[1])
        least_drawn = min(stats["cards_drawn"].items(), key=lambda x: x[1])
        all_cards = set(active_cards.keys())
        drawn_cards_set = set(stats["cards_drawn"].keys())
        never_drawn = all_cards - drawn_cards_set
        if never_drawn:
            least_drawn = (list(never_drawn)[0], 0)
        cards_text = f"**Most Drawn:** {most_drawn[0]} ({most_drawn[1]} times)\n**Least Drawn:** {least_drawn[0]} ({least_drawn[1]} times)"
    else:
        cards_text = "No card data yet"

    embed = discord.Embed(title="📊 Reading Statistics", color=discord.Color.gold())
    embed.add_field(name="📈 Total Readings", value=str(stats["total_readings"]), inline=True)
    embed.add_field(name="🔥 Current Streak", value=f"{streak} day{'s' if streak != 1 else ''}", inline=True)
    embed.add_field(name="⭐ Most Active Day", value=f"{most_active_day[0]} ({most_active_day[1]} readings)", inline=True)
    embed.add_field(name="👥 Readings Per Person", value=person_text, inline=False)
    embed.add_field(name="🎴 Card Stats", value=cards_text, inline=False)

    await interaction.followup.send(embed=embed, ephemeral=True)

@tree.command(name="help", description="View all available commands and what they do")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🔮 Oracle of the Moon — Commands",
        description="Here's everything you can do with this bot:",
        color=discord.Color.purple()
    )

    embed.add_field(
        name="🎴 Drawing Cards",
        value=(
            "`/draw [count]` — Draw 1–5 cards from the deck and reveal them one by one\n"
            "`/ask [question]` — Draw a single card as an answer to your question\n"
            "`/pull_clarifier` — Draw an extra card to clarify your current reading"
        ),
        inline=False
    )

    embed.add_field(
        name="🔮 Spreads",
        value=(
            "`/spread [type]` — Perform a 3-card spread (Past/Present/Future, Mind/Body/Spirit, or Situation/Action/Outcome)\n"
            "`/custom_spread [name] [positions]` — Create your own spread with custom position names (comma-separated, up to 10)"
        ),
        inline=False
    )

    embed.add_field(
        name="👥 Reading for Others",
        value=(
            "`/reading_for [user] [type]` — Perform a reading for another server member\n"
            "`/request_reading [topic]` — Request a reading from the Wasteland Oracle"
        ),
        inline=False
    )

    embed.add_field(
        name="🃏 Deck Management",
        value=(
            "`/shuffle` — Fully reset the deck and shuffle all cards back in\n"
            "`/shuffle_remaining` — Shuffle only the cards still in the deck, keeping drawn cards out\n"
            "`/undo` — Return the last drawn cards to the top of the deck\n"
            "`/undo_and_shuffle` — Return the last drawn cards and shuffle the whole deck\n"
            "`/deck_info` — See how many cards are in the deck and how many remain\n"
            "`/deck_list` — View all available decks\n"
            "`/deck_switch [name]` — Switch to a different deck"
        ),
        inline=False
    )

    embed.add_field(
        name="📖 Journal",
        value=(
            "`/journal [name] [notes]` — Save your last reading with personal notes\n"
            "`/journal_view` — Browse all your journal entries\n"
            "`/journal_view [name]` — View a specific journal entry by name\n"
            "`/journal_delete [name]` — Delete a journal entry"
        ),
        inline=False
    )

    embed.add_field(
        name="🌅 Daily & Stats",
        value=(
            "`/daily_card [channel]` — Draw a daily card and post it (with your interpretation) to a channel\n"
            "`/reading_stats` — View statistics about your readings and card history\n"
            "`/card_info [name]` — Look up the meaning of any card without drawing it"
        ),
        inline=False
    )

    embed.add_field(
        name="✦ Emergent & Manifested Draws",
        value=(
            "Occasionally, a card may slip free during a shuffle and reveal itself.\n\n"
            "**Emergent Draw** *(1.25% chance on shuffle)* — A single card tumbles loose "
            "and is displayed face-up before being removed from the deck.\n\n"
            "**Manifested Draw** *(0.25% chance on shuffle)* — Two cards slip free at once, "
            "both displayed face-up before being removed from the deck.\n\n"
            "*It happens with physical decks too. The cards have their own ideas.*"
        ),
        inline=False
    )

    embed.set_footer(text="✨ The cards are always listening.")
    await interaction.response.send_message(embed=embed, ephemeral=True)

@client.event
async def on_ready():
    load_decks_from_github()
    await tree.sync()
    print(f'✅ Logged in as {client.user}')
    print(f'🔮 Oracle card bot ready!')
    print(f'📦 Loaded {len(loaded_decks)} deck(s): {", ".join(loaded_decks.keys())}')
    print(f'📝 Commands: /shuffle, /shuffle_remaining, /draw, /ask, /spread, /custom_spread, /reading_for, /pull_clarifier, /undo, /undo_and_shuffle, /deck_info, /deck_list, /deck_switch, /card_info, /journal, /journal_view, /journal_delete, /reading_stats, /daily_card, /request_reading, /help')

# Run the bot
client.run(os.getenv('DISCORD_TOKEN'))

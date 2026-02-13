# Oracle Card Discord Bot 🔮

A Discord bot for interactive card readings with face-down dealing, one-by-one reveals, and card images!

## Features

- **`/shuffle`** - Reset and shuffle the deck
- **`/draw [count]`** - Draw 1-5 cards with flip buttons
- **`/spread [type]`** - Perform preset spreads:
  - Past • Present • Future
  - Mind • Body • Spirit  
  - Situation • Action • Outcome
- **`/deck_info`** - See deck details and card counts
- **Interactive reveals** - Click buttons to flip cards one at a time!
- **Card images** - Automatically displays images from your GitHub repo!

## Current Deck

Demo deck includes 21 Major Arcana tarot cards with basic meanings.

## Setting Up Card Images

### 1. Prepare Your Images

- Save card images with names matching the card names (lowercase, hyphens for spaces)
- Examples:
  - "The Fool" → `the-fool.jpg`
  - "The High Priestess" → `the-high-priestess.jpg`
- Supported formats: `.jpg` or `.png`

### 2. Add Images to Your Repo

```
your-repo/
├── oracle_bot.py
├── requirements.txt
└── card_images/           ← Create this folder
    ├── the-fool.jpg
    ├── the-magician.jpg
    ├── the-high-priestess.jpg
    └── ...
```

### 3. Update Bot Configuration

Edit these lines at the top of `oracle_bot.py`:

```python
GITHUB_USERNAME = "yourusername"  # Your GitHub username
GITHUB_REPO = "yourrepo"          # Your repository name
GITHUB_BRANCH = "main"            # Usually 'main' or 'master'
IMAGE_FOLDER = "card_images"      # Folder where images are stored
```

### 4. Push to GitHub

```bash
git add card_images/
git commit -m "Add card images"
git push
```

That's it! The bot will automatically generate the correct URLs and display images when cards are revealed.

## Customizing for Your Oracle Deck

To add your friend's actual oracle cards:

1. **Edit the `CARDS` dictionary** in `oracle_bot.py`:
   ```python
   CARDS = {
       "Card Name": "Card meaning/description",
       "Another Card": "Its meaning here",
       # ... add all cards
   }
   ```

2. **Add corresponding images** to the `card_images/` folder with matching filenames

3. **Customize spreads** - Add more spread types in the `spread` command

## Image File Naming

The bot converts card names to filenames automatically:
- Converts to lowercase
- Replaces spaces with hyphens
- Removes special characters like `•`

Examples:
- "The Fool" → `the-fool.jpg`
- "Wheel of Fortune" → `wheel-of-fortune.jpg`

**Important:** If using `.png` files instead of `.jpg`, update this line in the code:
```python
filename = f"{filename}.png"  # Change .jpg to .png
```

## Setup

```bash
pip install discord.py
python oracle_bot.py
```

## Deployment

Push to GitHub and deploy on Railway - images and code will auto-update when you push changes!

---

**Note:** This is a demo version. Work with your friend to customize the deck and add her oracle cards! ✨

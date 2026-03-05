# AI Finance Agent — Telegram to Google Sheets & Notion

Track your expenses by just sending a message to Telegram.
No forms. No spreadsheet opening. Just chat.

---

## What it does

Send something like:

> "spent 250 baht on lunch today"

The AI reads it, figures out the category, and logs it to Google Sheets and Notion automatically.
Then sends back a summary of your total spending.

That's it.

---

## How it works

```
Telegram message
      ↓
AI Agent (Ollama) reads and extracts data
      ↓
Splits into individual transactions
      ↓
Saves to Google Sheets + Notion
      ↓
Sends summary back to Telegram
```

---

## Tools used

- **n8n** — workflow automation
- **Telegram Bot** — input trigger + response
- **Ollama (llama3.2)** — local AI model (free, no API costs)
- **Google Sheets** — expense logging
- **Notion** — database backup

> You can swap Ollama for OpenAI, Groq, or any other model. The workflow supports any LLM.

---

## Setup

**1. Telegram Bot**
- Create a bot via @BotFather
- Copy the bot token
- Add it to the Telegram Trigger node credentials

**2. Ollama**
- Install Ollama → [ollama.ai](https://ollama.ai)
- Run: `ollama pull llama3.2`
- Make sure it's running locally before activating the workflow

**3. Google Sheets**
- Create a new spreadsheet
- Add these column headers: `Date`, `Vendor`, `Amount`, `Currency`
- Replace `YOUR_GOOGLE_SHEETS_ID` in both Google Sheets nodes

**4. Notion**
- Create a new database with these properties:
  - `Vendor` (Title)
  - `Amount` (Number)
  - `Currency` (Text)
  - `Date` (Date)
  - `Category` (Select)
- Replace `YOUR_NOTION_DATABASE_ID` in the Notion node

**Setup time: ~15 minutes**

---

## Categories supported

`Food` `Transport` `Shopping` `Bills` `Health` `Entertainment` `Income` `Others`

The AI auto-detects the category from your message.

---

## Example messages

- "spent 500 baht on groceries"
- "KFC lunch 250 baht"
- "received salary 30000 baht"
- "paid electric bill 1200 baht and bought coffee 80 baht"

Multiple transactions in one message work too.

---

# AI Appointment Booking — Lead Scoring with Groq + Qdrant + Ollama

An AI-powered appointment booking system that scores leads automatically.
High-score leads get booked. Low-score leads get a polite rejection.
No manual filtering needed.

---

## What it does

Someone submits a booking request with their name, budget, and needs.

The AI reads it, checks it against your company rules, scores the lead from 0-100, then:
- Score 70+ → sends confirmation email + logs to Google Sheets as "Hot Accept"
- Score below 70 → sends rejection message + logs as "Cold" or "Hot Reject"

All automated. Zero manual work.

---

## How it works

```
Webhook (booking form submission)
      ↓
AI Agent (Groq) reads name, budget, needs
      ↓
Searches company rules from Qdrant Vector Store
      ↓
Scores the lead (0-100)
      ↓
If score >= 70 → Accept → Gmail + Google Sheets
If score < 70  → Reject → Telegram + Google Sheets
```

---

## Tools used

- **n8n** — workflow automation
- **Groq** — fast LLM for lead scoring
- **Qdrant** — vector store for company rules/pricing
- **Ollama** — local embeddings (free)
- **Gmail** — acceptance email
- **Telegram** — rejection notification
- **Google Sheets** — lead tracking (Hot Accept / Hot Reject / Cold)

> You can swap Groq for OpenAI or any other model. OpenAI node is included as alternative.

---

## Setup

**1. Webhook**
- Copy the webhook URL after activating
- Connect to your booking form

**2. Qdrant Vector Store**
- Set up Qdrant locally or use Qdrant Cloud
- Create a collection and upload your company rules/pricing
- Replace `YOUR_QDRANT_COLLECTION` in the vector store node

**3. Groq**
- Get free API key at console.groq.com
- Add to Groq Chat Model node credentials

**4. Ollama**
- Install Ollama → [ollama.ai](https://ollama.ai)
- Run: `ollama pull llama3.2`
- Used for embeddings only

**5. Gmail**
- Connect your Gmail account
- Customize the acceptance email template

**6. Google Sheets**
- Create a spreadsheet with columns: `Name`, `Budget`, `Needs`, `Score`, `Status`, `Date`
- Replace `YOUR_GOOGLE_SHEETS_ID` in all Google Sheets nodes

**7. AI Agent Prompt**
- Update the system prompt with your company name, services, and pricing
- This is what the AI uses to evaluate leads

**Setup time: ~30 minutes**

---

## Lead scoring logic

The AI scores based on how well the lead's budget and needs match your services.

You control the rules by what you put in Qdrant.

---

## Built by

Victor (Aung Hein Kyaw)
AI Automation & n8n Specialist — Bangkok 🇲🇲
[FYF AI Automation](https://www.facebook.com/FYFAIAutomation)

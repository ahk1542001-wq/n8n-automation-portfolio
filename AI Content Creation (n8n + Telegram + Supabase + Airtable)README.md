# ✍️ AI Content Creation  (n8n + Telegram + Supabase + Airtable)

An advanced, autonomous **n8n** workflow designed to act as your personal AI content team. You simply text an idea to your Telegram bot, and the system researches the topic, emulates your specific writing persona using RAG (Vector Embeddings), drafts a high-converting LinkedIn post, asks for your review via Telegram, and finally logs the data to both Supabase and Airtable.

## 🌟 Architecture & Workflow

1. **Idea Capture (Telegram):** You message a topic (e.g., "AI Agents in n8n") to your dedicated Telegram Bot.
2. **Research Phase (Firecrawl + Groq):** The **Researcher Agent** scrapes targeted websites (like the n8n blog) using Firecrawl and synthesizes technical facts and ROI value into a structured brief.
3. **Tone Cloning & Drafting (OpenAI + Qdrant):** The **Content Writer Agent** uses Ollama embeddings to query a **Qdrant Vector Store** containing your past writings. It then drafts a LinkedIn post matching your exact tone, vocabulary, and style.
4. **Human-in-the-Loop (HITL) Review:** The drafted post (Title & Content) is sent back to your Telegram as an interactive form. You can edit the text directly in Telegram, approve it, or type "skip" to discard.
5. **Multi-Database Logging:** Upon approval, the final edited version and the original draft are securely saved to both **Supabase** (Vault) and **Airtable** (Content Calendar).

---

## 🛠️ Tech Stack & Integrations

* **Workflow Engine:** [n8n](https://n8n.io/)
* **AI Agents / LLMs:** * Groq (Llama-3.3-70b) for rapid research synthesis.
  * OpenAI for high-quality content generation.
* **RAG / Vector Store:** Qdrant (Database) & Ollama (Local Embeddings - `nomic-embed-text`).
* **Web Scraping:** Firecrawl Tool.
* **Communication / UI:** Telegram Bot API.
* **Databases:** Supabase (PostgreSQL) & Airtable.

---

## 📂 Repository Contents

* `Content Creation Agent.json`: The sanitized n8n workflow file ready for import.

---

## ⚙️ Setup Instructions

### 1. Prerequisites
You will need API credentials for the following services:
* **Telegram:** Bot Token (from BotFather) and your personal Chat ID.
* **Groq & OpenAI:** API Keys for LLM routing.
* **Ollama:** A running Ollama instance with the `nomic-embed-text` model pulled.
* **Qdrant:** API URL and Key (Cloud or Local).
* **Firecrawl:** API Key for web scraping.
* **Supabase & Airtable:** API Keys/Tokens for database access.

### 2. Database Preparation
**Airtable Setup:** Create a table with the following string (long text) fields:
* `Final Title`
* `Draft Title`
* `Draft Content`
* `Final Content`

**Supabase Setup:** Create a table named `linkedin_posts` with the following columns:
* `final_title` (text)
* `final_content` (text)
* `draft_title` (text)
* `draft_content` (text)

**Qdrant Setup:** Ensure you have a collection (e.g., `victor-tone-memory`) populated with your previous posts/articles using the `nomic-embed-text` embedding model.

### 3. n8n Import & Configuration
1. Import the `.json` file into your n8n workspace.
2. Authenticate all credential nodes.
3. **Configure Nodes:**
   * **Telegram Trigger & Secure Pass:** Replace `YOUR_TELEGRAM_CHAT_ID_NUMBER` with your numerical Telegram Chat ID to ensure the bot only responds to you.
   * **Qdrant Vector Store:** Enter your exact Collection Name.
   * **Post Database (Supabase):** Select your table (`linkedin_posts`).
   * **Post Dashboard (Airtable):** Select your Base and Table.
4. **Activate the Workflow!**

---

## 🚀 How to Use
1. Open your Telegram Bot.
2. Send a simple message like: *"Write a post about the new n8n memory nodes."*
3. Wait ~15-30 seconds.
4. The bot will reply with a beautifully drafted post inside a form.
5. Review, make edits directly in the Telegram text box, and submit. (Or type `skip` in the content box to cancel).
6. Check your Airtable and Supabase to see the saved content!

---

## 🔒 Security Note
This workflow file has been strictly **sanitized**. All personal identifiers, Webhook URLs, database IDs, Telegram Chat IDs, and credential names have been replaced with placeholders (e.g., `YOUR_TELEGRAM_CRED_ID`). You must reconnect your own credentials after importing.

---

## 💡 Customization
* **Scraping Sources:** Open the `Researcher Agent` prompt and change the URL (currently set to `https://blog.n8n.io/`) to whatever domain you want the agent to scrape for facts.
* **LLM Swapping:** You can easily swap the OpenAI node for Anthropic (Claude) or another Groq node depending on your preference and API limits.

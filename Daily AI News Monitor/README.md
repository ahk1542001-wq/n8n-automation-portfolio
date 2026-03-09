# 📰 Autonomous AI News Monitor (n8n + Groq + Telegram)

An intelligent, fully automated **n8n** dual-workflow system that acts as your personal AI news anchor. It monitors top AI and tech blogs via RSS, filters out the noise, uses **Groq (Llama-3.3-70B)** to summarize the most important updates into concise bullet points, and delivers a beautifully formatted daily briefing directly to your Telegram.

## 🌟 Architecture & Workflow

This project utilizes an advanced **Main-Sub Workflow** architecture for scalability and error handling:

### 1. MAIN Workflow (The Controller)
* **Scheduler:** Runs automatically every day at a specified time (e.g., 7:00 AM).
* **Feed Definition:** Contains a Javascript node defining target RSS feeds (HuggingFace, OpenAI, n8n, The Rundown).
* **Iterator:** Passes each feed URL dynamically to the Sub-Workflow.
* **Aggregator & Delivery:** Collects all summarized outputs from the Sub-Workflow, formats them into a clean HTML message, and sends a single daily digest to your Telegram.
* **Error Handling:** Includes an `Error Trigger` node that alerts you via Telegram if any part of the automation fails.

### 2. SUB Workflow (The Engine)
* **RSS Fetcher:** Reads the specific feed URL passed from the Main workflow.
* **Data Parsing:** Extracts the latest 5 articles and cleans HTML tags from the content.
* **AI Summarization:** Passes the aggregated text to **Groq (Llama-3.3-70B)** via LangChain nodes. The AI is prompted to act as an expert analyst, ignoring non-AI news, and outputting exactly 3 concise bullet points (Currently set to Burmese, but fully customizable).
* **Return:** Sends the clean summary back to the Main workflow.

---

## 🛠️ Tech Stack & Integrations

* **Automation Engine:** [n8n](https://n8n.io/) (Self-hosted or Cloud)
* **AI / LLM:** [Groq](https://groq.com/) (Llama-3.3-70b-versatile for lightning-fast inference)
* **Data Source:** Standard RSS Feeds
* **Communication:** Telegram Bot API

---

## 📂 Repository Contents

* `MAIN - Daily AI News Monitor.json`: The primary controller workflow.
* `SUB - Scrape and Summarize (AI).json`: The processing and AI summarization workflow.

---

## ⚙️ Setup Instructions

### 1. Prerequisites
You will need API credentials for:
* **Groq:** API Key for the LLM node.
* **Telegram:** Bot Token (from BotFather) and your personal Chat ID.

### 2. n8n Import & Configuration
1. **Import Sub-Workflow:** First, import `SUB - Scrape and Summarize (AI).json` into your n8n workspace.
   * Authenticate your Groq API credential inside the LangChain model node.
   * Save the workflow and copy its **Workflow ID** from the URL or settings.
2. **Import Main-Workflow:** Next, import `MAIN - Daily AI News Monitor.json`.
   * Open the `Run Sub-Workflow` node and select the Sub-Workflow you just saved (or paste the ID).
   * Authenticate your Telegram credentials in both the `Send Daily News` and `Alert on Error` nodes.
   * Replace `YOUR_TELEGRAM_CHAT_ID` with your actual numerical Chat ID.
3. **Activate:** Toggle the MAIN workflow to **Active**. (You do not need to activate the SUB workflow, as it is triggered by the Main one).

---

## 🔒 Security Note
These workflow files have been strictly **sanitized**. All personal identifiers, Telegram Chat IDs, and credential names have been replaced with placeholders (`YOUR_...`). You must reconnect your own credentials after importing.

---

## 💡 Customization Guide
* **Add/Remove News Sources:** Open the `Define AI Feeds` node in the MAIN workflow. You can easily add any valid RSS feed URL to the JSON array.
* **Change the Output Language/Format:** Open the `Summarize with Groq` node in the SUB workflow. Modify the system message to change the output language (e.g., from Burmese to English) or change the summary format (e.g., "Write a 2-sentence summary" instead of bullet points).
* **Adjust Delivery Time:** Open the `Schedule Trigger` node in the MAIN workflow to change when you receive your daily brief.

---

## 🤝 Contributing
Feel free to fork this project, submit pull requests, or open issues if you find ways to optimize the LLM prompts or add new scraping capabilities!

# 🚀 Career Automation Agent (AI Job Search & Cover Letter Generator)

An advanced, fully automated n8n workflow that acts as your personal AI career assistant. It runs daily to search for jobs, evaluates them against your CV using LLMs, alerts you on Telegram for high-match roles, and generates custom cover letters upon your approval.

## 🌟 Overview

This intelligent automation saves hours of manual job hunting by:
1. **Fetching Criteria & CV:** Reads your target job title/location from Google Sheets and downloads your latest CV from Google Drive.
2. **Automated Job Search:** Uses SerpApi (Google Jobs) to scrape the latest job postings.
3. **AI Screening:** Uses Groq (Llama-3.1-8B) to compare the job description against your CV, outputting a `match_score` and `summary`.
4. **Human-in-the-Loop (HITL) Alerts:** If a job matches >70%, it sends a Telegram alert with the job details and asks for your approval.
5. **AI Cover Letter Generation:** If approved via Telegram, it uses Groq (Llama-3.3-70B) to write a highly tailored, 3-paragraph cover letter.
6. **Review & Save:** Sends the generated cover letter to Telegram for final editing and saves the application details into a Google Sheet CRM.

## 🛠️ Tech Stack
* **Automation Platform:** [n8n](https://n8n.io/)
* **AI / LLMs:** [Groq](https://groq.com/) (Llama-3.1-8B for rapid scoring, Llama-3.3-70B for high-quality writing)
* **Search Engine API:** [SerpApi](https://serpapi.com/) (Google Jobs API)
* **Messaging & HITL:** Telegram Bot API
* **Database & Storage:** Google Sheets & Google Drive

## 📂 Repository Contents
* `Career Automation Agent.json`: The sanitized n8n workflow file. You can import this directly into your n8n instance.

## ⚙️ Setup Instructions

### 1. Prerequisites
You will need API keys and accounts for the following services:
* Google Cloud Console (OAuth2 for Drive and Sheets)
* SerpApi (for Google Jobs search)
* Groq (for fast LLM inference)
* Telegram Bot Token (via BotFather) & your personal Telegram Chat ID

### 2. Google Workspace Setup
* **Google Drive:** Upload your CV in PDF format and copy the File URL/ID.
* **Google Sheet 1 (Search Criteria):** Create a sheet with columns: `job_title` | `location`
* **Google Sheet 2 (Job Tracker):** Create a tracking sheet with exactly these columns:
  `Job Title` | `Company` | `Link` | `Match Score` | `Summary` | `Date` | `Cover Ltter`

### 3. n8n Setup
1. Import the `Career Automation Agent.json` file into your n8n workspace.
2. Connect and authenticate all your credentials (Google Drive, Google Sheets, SerpApi, Groq, Telegram).
3. **Configure Nodes:**
   * Update the `Download CV from Drive` node with your CV's file ID or URL.
   * Update the `Get Search Criteria from Sheet` and `Save to Google Sheet` nodes to point to your respective Google Sheets.
   * Update the `Telegram` nodes with your personal `Chat ID`.
4. The workflow is set to run automatically every day at 21:00 (9:00 PM). You can adjust this in the `Schedule Trigger` node.
5. Toggle the workflow to **Active**.

## 🔒 Security Note
This workflow file has been strictly sanitized. All personal IDs, Webhook URLs, Telegram Chat IDs, and credential names have been replaced with placeholders like `YOUR_TELEGRAM_CHAT_ID` or `YOUR_GROQ_CRED_ID`. You will need to select your own credentials after importing.

## 💡 Customization
* **Threshold Adjustment:** You can change the passing match score in the `If Score >= 70` node to make the filter stricter or looser.
* **Prompt Tuning:** Open the `AI Agent` nodes to tweak the system prompts if you want a different tone or specific focus areas for your cover letters.

## 🤝 Contributing
Feel free to fork this project, submit pull requests, or open issues if you find ways to optimize the prompts or expand the workflow's capabilities!

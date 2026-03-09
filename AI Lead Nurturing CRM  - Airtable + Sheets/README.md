# 🤖 AI Lead Nurturing CRM (Airtable + Google Sheets + Gmail)

A fully automated, AI-driven Lead Management and Nurturing System built on **n8n**. This workflow captures leads, uses **Groq (Llama-3.3-70B)** to intelligently score and qualify them, syncs data across **Airtable** and **Google Sheets**, alerts your team via **Telegram**, and executes a personalized 7-day email drip campaign via **Gmail**.

## 🌟 Key Features

* **📝 Automated Lead Capture:** Uses an n8n native Webhook Form to collect lead information (Name, Company, Email, Budget, Needs).
* **🧠 AI Scoring & Qualification:** Analyzes the lead's budget and business needs to assign a score (0-100) and categorizes them into Hot, Warm, or Cold tiers.
* **✍️ AI Email Generation:** Automatically writes a highly personalized 3-part email sequence (Day 1, Day 3, Day 7) tailored to the lead's specific pain points.
* **🔄 Dual CRM Syncing:** Seamlessly logs and updates lead data in both Google Sheets (for tracking) and Airtable (for pipeline management). Includes duplicate checking!
* **⚡ Instant Notifications:** Sends real-time Telegram alerts for invalid emails, high-value "Hot Leads" (Score >= 70), and sequence completion summaries.
* **⏳ 7-Day Drip Campaign:** Automatically spaces out follow-up emails using `Wait` nodes, concluding with a final update to the Airtable CRM status.

---

## 🛠️ Tech Stack & Integrations

* **Workflow Automation:** [n8n](https://n8n.io/)
* **AI Model:** [Groq](https://groq.com/) (Llama-3.3-70b-versatile for fast, high-quality reasoning and generation)
* **Databases:** Airtable & Google Sheets
* **Communication:** Telegram (Internal Alerts) & Gmail (Client Outreach)

---

## 📂 Repository Contents

* `AI Lead Nurturing CRM - Airtable + Sheets.json`: The sanitized n8n workflow file. You can import this directly into your n8n workspace.

---

## ⚙️ Setup Instructions

### 1. Prerequisites
You will need active accounts and API credentials for:
* **Groq** (API Key)
* **Airtable** (Personal Access Token)
* **Google Cloud Console** (OAuth2 credentials for Gmail and Google Sheets)
* **Telegram** (Bot Token via BotFather & your personal Chat ID)

### 2. Database Preparation
**Airtable Setup:** Create a base with a table containing the following fields:
* `id` (Record ID - handled by Airtable)
* `Name` (Single line text)
* `Email` (Email)
* `Company` (Single line text)
* `Budget` (Single line text)
* `Needs` (Long text)
* `Score` (Number)
* `Reason` (Single line text)
* `Deal Name` (Single line text)
* `Deal AmountN` (Number / Currency)
* `Status` (Single line text or Single select)
* `Date` (Date)

**Google Sheets Setup:** Create a sheet with the following exact column headers in Row 1:
* `Lead ID` | `Name` | `Email` | `Company` | `Budget` | `Needs` | `Score` | `Tier` | `Reason` | `Status` | `Date`

### 3. n8n Import & Configuration
1. Open your n8n instance and click **Import from File**. Upload the provided `.json` file.
2. Authenticate all credential nodes (Groq, Airtable, Google Sheets, Gmail, Telegram).
3. **Configure Nodes:**
   * **Airtable Nodes:** Select your specific Base and Table from the dropdowns (or enter your Base/Table IDs).
   * **Google Sheets Node:** Provide the URL or Document ID of your tracking sheet.
   * **Telegram Nodes:** Replace `YOUR_TELEGRAM_CHAT_ID` with your actual Telegram Chat ID.
4. **Activate the Workflow:** Once all credentials and IDs are set, toggle the workflow to **Active**.
5. Copy the **Production URL** from the `Form: Consultation Request` trigger node to start capturing leads!

---

## 🔒 Security Note
This workflow file has been **sanitized**. All personal identifiers, Webhook URLs, Google Sheet IDs, Airtable Base IDs, Telegram Chat IDs, and credential names have been replaced with placeholders like `YOUR_AIRTABLE_BASE_ID`. When you import this into your own n8n instance, simply reconnect your credentials to auto-populate your secure keys.

---

## 💡 Customization Guide
* **Adjusting Lead Score:** Open the `IF: Hot Lead? (Score >= 70)` node. You can change the `70` to whatever threshold fits your business model.
* **Modifying the AI Prompt:** Open the `AI Agent: Score + Generate Email Sequence` node. You can edit the system prompt to change the tone of the emails, adjust the budget-to-score logic, or modify the expected output schema.
* **Changing Wait Times:** Modify the `Wait: 2 Days` and `Wait: 4 Days` nodes to stretch or shorten your email drip campaign.

---

## 🤝 Contributing
Feel free to fork this project, submit pull requests, or open issues if you find ways to optimize the LLM prompts or expand the CRM's capabilities!

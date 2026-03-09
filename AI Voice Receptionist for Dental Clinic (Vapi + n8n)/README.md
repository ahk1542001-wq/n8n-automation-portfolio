# 🦷 AI Voice Receptionist for Dental Clinic (Vapi + n8n)

An intelligent, fully automated AI voice receptionist built for dental clinics. This project uses **Vapi** for the conversational AI voice agent and **n8n** as the backend automation router to interact seamlessly with **Google Sheets** (as a CRM) and **Google Calendar** (for appointment scheduling).

## 🚀 Overview

This system allows patients to call the clinic and speak to an AI assistant that can naturally:
1. Look up existing patient records.
2. Check available time slots on the clinic's real-time calendar.
3. Book new appointments (saves to CRM and Calendar).
4. Reschedule existing appointments.
5. Cancel appointments and free up the calendar slot.

## 🛠️ Tech Stack
* **Voice AI Engine:** [Vapi](https://vapi.ai/) (using ElevenLabs voices & GPT-4o-mini / Claude 3.5 Sonnet)
* **Automation Backend:** [n8n](https://n8n.io/) (Webhook Router & Logic)
* **Database / CRM:** Google Sheets
* **Scheduling:** Google Calendar

## 📂 Repository Contents

This repository contains sanitized n8n workflow JSON files. You can import these directly into your n8n instance.

1. `MAIN - Vapi MCP Router.json`: The central webhook receiver that routes Vapi tool calls to the correct sub-workflow.
2. `SUB - Client Lookup.json`: Searches Google Sheets by Name or Phone.
3. `SUB - Check Availability.json`: Checks Google Calendar for conflicts.
4. `SUB - Book Appointment.json`: Creates a calendar event and appends a row to Google Sheets.
5. `SUB - Update Appointment.json`: Updates an existing calendar event and modifies the CRM record.
6. `SUB - Delete Appointment.json`: Deletes a calendar event and marks the CRM record as 'Canceled'.

## ⚙️ Setup Instructions

### 1. Google Workspace Setup
* Create a new **Google Calendar** specifically for clinic bookings (e.g., "Clinic Bookings").
* Create a **Google Sheet** to act as your CRM.
* **Important:** Your Google Sheet must contain the following exact column headers in Row 1:
  * `Name` | `Phone` | `Date` | `Time` | `Reason` | `Status` | `Patient ID` | `Last Visit`

### 2. n8n Setup
1. Import all 6 JSON workflows into your n8n instance.
2. Set up **Google OAuth2 Credentials** in n8n for both Google Calendar and Google Sheets API.
3. Go through each sub-workflow and select your Google Sheet and Google Calendar from the dropdowns in the respective nodes.
4. Open the `MAIN - Vapi MCP Router` workflow. Note down the **Production Webhook URL**.
5. Activate all workflows.

### 3. Vapi Setup
1. Create a new Assistant in Vapi.
2. Add your System Prompt (defining the persona, clinic details, and rules).
3. Under the **Tools** section, add 5 Custom Tools (Webhooks). 
4. Use the same **n8n Production Webhook URL** for all 5 tools.
5. Name the tools EXACTLY as follows to match the n8n router logic:
   * `client_lookup`
   * `check_availability`
   * `book_appointment`
   * `update_appointment`
   * `delete_appointment`
6. Provide the appropriate JSON Schema for each tool's parameters.

## 🔒 Security Note
These workflow files have been sanitized. All personal webhook IDs, Google Sheet IDs, and credential IDs have been replaced with placeholders like `YOUR_WEBHOOK_ID_HERE`. When you import these into your own n8n instance and select your credentials/files, n8n will automatically generate your unique IDs.

## 🤝 Contributing
Feel free to fork this project, submit pull requests, or open issues if you find ways to optimize the n8n logic or Vapi tool schemas!

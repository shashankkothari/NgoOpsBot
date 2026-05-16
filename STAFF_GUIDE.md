# NGO OpsBot — Staff Guide

This guide explains how to use NGO OpsBot on the staff portal and Telegram. Use the Helper agent (or `/help` on Telegram) to ask questions about using the platform at any time.

---

## What is NGO OpsBot?

NGO OpsBot is an AI assistant built specifically for NGO staff in India. It gives you access to specialist agents — each one an expert in a different part of your work. You can talk to them on Telegram (in your NGO group) or through the staff portal (a website your admin gave you a link to).

The agents can look up real data from your NGO's Google Sheets, search emails, create calendar reminders, draft emails for your review, and answer questions based on Indian NGO regulations.

---

## Your Agents

### 💰 Fundraising Agent
Handles everything related to donors, grants, and fundraising campaigns.

**Ask it things like:**
- "Which donors haven't given in the last 6 months?"
- "What's the utilisation percentage on the Azim Premji grant?"
- "Draft a re-engagement email for Ramesh Kumar who donated ₹25,000 last year"
- "Generate an 80G receipt for Priya Sharma's donation of ₹50,000"
- "When is the reporting deadline for our Ford Foundation grant?"

**It can:** Read your Donors and Grants tabs in Google Sheets, draft emails (saved to Gmail Drafts for you to review — it never sends automatically), calculate donor retention rates and grant utilisation.

**It cannot:** Process payments, access bank accounts, confirm tax deductibility for specific donors.

---

### 📊 Finance Agent
Handles budgets, expenses, invoices, and financial reporting.

**Ask it things like:**
- "What's our actual vs budget for Q3?"
- "Which expense categories are overspent this month?"
- "Prepare a board summary for November finances"
- "What's the TDS rate on contractor payments above ₹30,000?"
- "How much have we spent against the Infosys CSR grant?"

**It can:** Read your Finance and Grants tabs in Google Sheets, calculate variances and percentages, explain TDS rules and audit requirements for Indian NGOs.

**It cannot:** Make payments, approve expenses, access your bank account or Tally directly.

---

### 👥 HR Agent
Handles staff management, leave tracking, volunteer coordination, and recruitment.

**Ask it things like:**
- "Priya has applied for 3 days earned leave from Dec 15–17 — what's her balance?"
- "Draft an offer letter for a Program Officer at ₹45,000/month"
- "Create a volunteer onboarding checklist for our health camp"
- "Is Ravi eligible for gratuity after 4.5 years of service?"
- "Who is on leave this week?"

**It can:** Read your Staff tab in Google Sheets, draft offer letters and onboarding documents, explain Indian labour law basics for NGOs.

**It cannot:** Process payroll, access HR systems directly, make hiring or firing decisions.

---

### 📣 Marketing Agent
Handles communications, social media content, and donor-facing messaging.

**Ask it things like:**
- "Write a LinkedIn post about our school library project impact"
- "Draft a WhatsApp message for our year-end fundraising campaign"
- "What should our newsletter focus on this month?"
- "Write 3 Instagram captions for photos from our health camp"
- "Help me write an impact story about the children we served"

**It can:** Write content for social media, email campaigns, newsletters, and donor reports. Search the web for sector trends and benchmarks.

**It cannot:** Post directly to social media — it drafts content for you to post.

---

### ⚖️ Compliance Agent
Handles legal filings, regulatory compliance, and important deadlines.

**Ask it things like:**
- "When is the FC-4 annual return due?"
- "What documents do we need for our 80G renewal?"
- "Our CSR grant requires a utilisation certificate — what should it contain?"
- "Add a reminder for our FCRA renewal 3 months before the deadline"
- "What are the rules for sub-granting to another organisation under FCRA?"

**It can:** Answer questions about FCRA, 12A/80G, ITR-7, CSR compliance, and statutory audit requirements. Create calendar reminders for filing deadlines. Look up current regulatory information online.

**It cannot:** File documents on your behalf, give legal advice specific to your situation — always verify with your CA or legal advisor.

---

## The Staff Portal

### Chat page
This is where you talk to agents. On the left sidebar you'll see which agents are available to you — click one to start a conversation with it. Each agent remembers your conversation history separately.

The **reset button** (↺) at the top right starts a fresh conversation with the current agent. Use this when you want to start a completely new topic.

Press **Enter** to send a message, **Shift+Enter** for a new line.

### Reminders page
Shows all your reminders. You can:
- **Create** a reminder with a title, description, date, and repeat schedule
- **Snooze** a reminder (1 hour, 4 hours, 1 day, or 3 days)
- **Acknowledge** a reminder when it's done — it moves to the Completed section

Overdue reminders show in red. The agents can also create reminders for you during a conversation.

### Help & Support page
Submit a support request if you have a problem the agents can't solve, or if something isn't working. Set the category and priority, describe the issue, and submit. You'll be notified when your admin replies.

---

## Using Telegram

Add the bot to your NGO's Telegram group and mention it by name to talk to it.

**Example messages:**
```
@YourBot which donors haven't given this year?
@YourBot draft a thank you message for our Diwali donation drive
@YourBot what's our budget vs actuals for November?
```

The bot automatically routes your message to the right agent. If you want a specific agent, mention it:
```
@YourBot [Finance] prepare a board report for October
@YourBot [HR] who is on leave next week?
```

**Slash commands:**
- `/help` — opens a conversation with the Helper to answer your questions about using the bot
- `/status` — shows whether Google is connected and which agents are active
- `/myaccess` — shows which agents you have permission to use

---

## Tips for better results

**Be specific.** The more detail you give, the better the answer.
- ✅ "Draft a re-engagement email for Ramesh Kumar who donated ₹25,000 to our education project in March 2023"
- ❌ "Write a donor email"

**Give context for drafts.** If you want an email drafted, tell the agent the donor's name, the amount, what it was for, and the tone you want.

**Ask follow-up questions.** The agent remembers your conversation. If the first answer isn't quite right, say "make it shorter" or "add the FCRA bank account details" and it will revise.

**For Google Sheets data,** the agent reads directly from your Master Tracker. If the data isn't there, the agent won't have it. Keep your Sheets updated for the best results.

**Drafts are never sent automatically.** When the agent says "I've created a draft," it means the email is saved in Gmail Drafts. Open Gmail to review it before sending.

---

## Common questions

**Did the email send?**
No — the agents never send emails automatically. When the agent says "draft created," open Gmail Drafts to review and send it yourself.

**Why did the agent say it has no data?**
Either your Google Sheets isn't connected (your admin needs to do this from the dashboard), or the relevant tab is empty. Try asking what data is available and populate the Sheets first.

**Can the agent approve expenses or transfer money?**
No. The agents can track, report, and draft — but they cannot approve, execute, or access any payment system.

**Why am I getting a "not connected" error?**
Your NGO's Google account isn't linked yet. Ask your admin to connect it from the admin dashboard. Until then, you can still use the agents for general questions — they just won't have access to your Sheets, Gmail, or Calendar.

**I asked a question and got a wrong answer.**
The agents are powerful but not perfect. For regulatory questions (FCRA, TDS, audit), always verify with your CA or legal advisor. The agents will tell you when something needs professional confirmation.

**Can I use the portal and Telegram at the same time?**
Yes — your conversation history is shared. If you start a conversation with the Finance agent on Telegram, you'll see the same thread in the portal.

**What languages can I use?**
You can message in English, Hindi, or most regional languages. The agent will respond in the same language you use.

---

## When you're stuck

1. Ask the Helper agent — it knows this platform well.
2. Submit a support ticket from the Help & Support page.
3. Your admin can also submit tickets on your behalf.

The support team will get back to you as quickly as possible.

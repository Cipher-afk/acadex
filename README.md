# Acadex Bot 🎓

A Telegram bot that lets students access their university portal documents 
directly from Telegram — no browser needed.

## What it does
Send your portal credentials to the bot, and it fetches your:
- Exam results
- Registered courses  
- Payment receipts

All delivered instantly in your Telegram chat.

## Tech Stack
- **aiogram 3** — Telegram bot framework
- **Playwright** — headless browser automation for portal scraping
- **FastAPI** — backend API
- **Paystack** — payment integration
- **Python 3.13**

## How it works
1. Student sends credentials via Telegram
2. Bot logs into the university portal using Playwright
3. Fetches requested documents
4. Sends them back as images/files in chat

## Status
🚀 Live — deployed on Oracle Cloud (ARM)

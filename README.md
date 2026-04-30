# Acadex Bot 🎓

A Telegram bot for Federal University of Otueke, Bayelsa (FUO) students access their university portal documents 
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

## Demo
![Acadex Bot Demo]:<img width="478" height="1014" alt="acadex_video_gif" src="https://github.com/user-attachments/assets/0eab58f0-a7be-4d6b-8d21-11f1adb4847e" />

## Status
🚀 Live — deployed on Oracle Cloud (ARM)

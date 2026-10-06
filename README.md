# NutriSnap setup
1. Get an API key at console.anthropic.com (billing needed; each photo or plan costs a small amount).
2. Streamlit Cloud: open your app, Settings > Secrets, paste:
   ANTHROPIC_API_KEY = "your-key-here"
3. Local run: create .streamlit/secrets.toml with the same line, then `streamlit run app.py`.
Keep the app private so others can't use your key's credit.

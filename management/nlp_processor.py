import os
import re
import json
import logging
from google import genai
from dotenv import load_dotenv

load_dotenv()

class NLPProcessor:
    def __init__(self):
        self.use_ai = os.getenv("USE_AI_INTENT", "False").lower() in ("true", "1", "yes")
        self.api_key = os.getenv("GEMINI_API_KEY", "")

        if self.use_ai and self.api_key:
            self.client = genai.Client(api_key=self.api_key)
            # for model in self.client.models.list():
            #     print(model)
            logging.info("NLP Processor initialized with Gemini AI enabled.")
        else:
            if self.use_ai and not self.api_key:
                logging.warning("USE_AI_INTENT is True but GEMINI_API_KEY is not set. Falling back to local intent matching.")
            self.use_ai = False
            logging.info("NLP Processor initialized with Local Intent Matching enabled.")

    async def determine_intent(self, text: str):
        """
        Determines the intent and query from the text.
        Returns a tuple: (intent_name, query_string)
        intent_name can be: play, pause, resume, skip, stop, loop, disconnect, unknown
        """
        if self.use_ai:
            try:
                return await self.process_ai_intent(text)
            except Exception as e:
                logging.error(f"AI Intent extraction failed: {e}. Falling back to local.")
                return self.process_local_intent(text)
        else:
            return self.process_local_intent(text)

    async def process_ai_intent(self, text: str):
        prompt = f"""
You are a music bot intent classifier.
The user will provide a command in English or Hindi (or Hinglish).
Your job is to classify the command into one of the following intents:
- 'play' (to play a song, also extract the song name). IMPORTANT: Only classify as 'play' if the user explicitly asks to play something (e.g., using words like "play", "baja", "chala"). A sentence just saying a word or name (e.g. "Jarvis watermelon") with no intent to play must NOT be classified as 'play'.
- 'pause' (to pause the music)
- 'resume' (to resume paused music)
- 'skip' (to skip to the next song)
- 'stop' (to stop the music and clear the queue)
- 'loop' (to loop the current song)
- 'disconnect' (to disconnect the bot from voice)
- 'unknown' (if the command is not related to music controls or lacks a clear intent)

Return the result as a strict JSON object with exactly two keys:
1. "intent": string (one of the intents above)
2. "query": string (the name of the song if the intent is 'play', otherwise an empty string "")

Do not include markdown blocks or any other text, just the raw JSON.

User command: "{text}"
        """
        try:
            response = await self.client.aio.models.generate_content(
                model='gemma-4-31b-it',
                contents=prompt
            )
            # Remove any markdown formatting if present
            raw_json = re.sub(r'```json\n|\n```|```', '', response.text).strip()
            result = json.loads(raw_json)
            intent = result.get('intent', 'unknown').lower()
            query = result.get('query', '')

            valid_intents = ['play', 'pause', 'resume', 'skip', 'stop', 'loop', 'disconnect']
            if intent not in valid_intents:
                intent = 'unknown'

            return intent, query
        except Exception as e:
            raise Exception(f"Error calling Gemini API or parsing response: {e}")

    def process_local_intent(self, text: str):
        text = text.lower().strip()

        # Regex and word matching
        # English and Hindi keywords
        play_pattern = re.compile(r'\b(play|baja|chala|lagao|start)\b', re.IGNORECASE)
        pause_pattern = re.compile(r'\b(pause|rok de|rok do|ruko|wait)\b', re.IGNORECASE)
        resume_pattern = re.compile(r'\b(resume|continue|phir se|wapas|chalu kar)\b', re.IGNORECASE)
        skip_pattern = re.compile(r'\b(skip|next|dusra|agla|hatao)\b', re.IGNORECASE)
        stop_pattern = re.compile(r'\b(stop|band kar|band karo|khatam)\b', re.IGNORECASE)
        loop_pattern = re.compile(r'\b(loop|repeat|baar baar|phir se baja)\b', re.IGNORECASE)
        disconnect_pattern = re.compile(r'\b(disconnect|leave|nikal|jawa|jao|chale jao)\b', re.IGNORECASE)

        # Check intent
        if play_pattern.search(text):
            # Extract query: remove the keyword and everything before it, or just replace the keyword
            query = play_pattern.sub('', text).strip()
            # If the user says "play" at the beginning, the rest is the query
            match = play_pattern.search(text)
            if match:
                # get everything after the match
                query = text[match.end():].strip()
            return 'play', query

        if pause_pattern.search(text):
            return 'pause', ""

        if resume_pattern.search(text):
            return 'resume', ""

        if skip_pattern.search(text):
            return 'skip', ""

        if stop_pattern.search(text):
            return 'stop', ""

        if loop_pattern.search(text):
            return 'loop', ""

        if disconnect_pattern.search(text):
            return 'disconnect', ""

        return 'unknown', ""

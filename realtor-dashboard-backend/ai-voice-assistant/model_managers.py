# Singleton Model Managers for Heavy AI Components
# Provides centralized access to Spacy NLP models and Gemini AI throughout the application.
# Initialized once at startup (via initialization.py) then reused across all voice processing sessions.

import os
from dotenv import load_dotenv
import google.generativeai as genai
import spacy
from spacy.matcher import Matcher

class SpacyManager:
    _instance = None
    _nlp = None
    _matcher = None

    @classmethod
    def get_nlp(cls, force_load=False):
        if cls._nlp is None or force_load:
            try:
                cls._nlp = spacy.load('en_core_web_sm')
            except Exception as e:
                print(f"Error loading Spacy model: {e}")
                raise
        return cls._nlp

    @classmethod
    def get_matcher(cls):
        if cls._matcher is None:
            nlp = cls.get_nlp()
            cls._matcher = Matcher(nlp.vocab)
        return cls._matcher

    @classmethod
    def reset(cls):
        """Reset the singleton (mainly for testing)"""
        cls._nlp = None
        cls._matcher = None

class GeminiManager:
    _api_configured = False
    _model = None

    @classmethod
    def configure_api(cls, force_configure=False):
        if not cls._api_configured or force_configure:
            try:
                load_dotenv(dotenv_path='.env.docker')
                api_key = os.getenv('GOOGLE_API_KEY')
                if not api_key:
                    raise ValueError("GOOGLE_API_KEY environment variable not set")
                genai.configure(api_key=api_key)
                cls._api_configured = True
            except Exception as e:
                print(f"Error configuring Gemini API: {e}")
                raise

    @classmethod
    def create_chat(cls):
        """Create a new chat session for each conversation"""
        try:
            cls.configure_api()
            model = genai.GenerativeModel('gemini-1.5-flash')
            chat = model.start_chat(history=[])
            return model, chat
        except Exception as e:
            print(f"Error creating Gemini chat session: {e}")
            raise

    @classmethod
    def reset(cls):
        """Reset the API configuration (mainly for testing)"""
        cls._api_configured = False


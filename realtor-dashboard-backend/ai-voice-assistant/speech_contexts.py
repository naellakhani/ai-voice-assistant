
# This module centralizes all speech contexts used by Google Speech-to-Text to improve transcription accuracy for the voice calling system.

from google.cloud import speech_v1 as speech

# Basic alphabet and numbers for spelling
INDIVIDUAL_LETTERS = [
    "a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k", "l", "m",
    "n", "o", "p", "q", "r", "s", "t", "u", "v", "w", "x", "y", "z",
    "0", "1", "2", "3", "4", "5", "6", "7", "8", "9"
]

# Commonly mistranscribed letter pairs that need disambiguation
CONFUSED_LETTER_PAIRS = [
    "b not d", "d not b", "p not b", "b not p",
    "m not n", "n not m", "s not f", "f not s",
    "i not e", "e not i", "a not e", "e not a",
    "g not j", "j not g", "t not d", "d not t",
    "v not b", "b not v", "th not f", "f not th",
    "c not s", "s not c", "k not c", "c not k",
    "p not c", "c not p", "p not t", "t not p",
    "ez", "ez not is that", "e z not easy",
    "b c", "b c not busy",
]

confused_words = [
        "know", "no", "now", "new", "knew", "nose", "knows",
        "there", "their", "they're", "here", "hear", "where", "wear",
        "right", "write", "rite", "wright", "to", "too", "two", "for", "four", "fore",
        "send", "sent", "scent", "cent", "buy", "by", "bye", "hi", "high",
        "mail", "male", "see", "sea", "scene", "seen", "be", "bee", "are", "our",
        "your", "you're", "you", "you'll", "your", "you're", "your", "you're"
]

context_disambiguated_phrases = [
        # No vs. Know
        "I know the answer", "I don't know", "Do you know", "Let me know",
        "No thank you", "No that's not right", "No I don't", "Yes or no",
        
        # Their vs. There vs. They're
        "Their company", "Their email", "Their phone number", 
        "Over there", "Right there", "There it is",
        "They're coming", "They're available", "They're based in",
        
        # To vs. Too vs. Two
        "Send it to me", "Talk to you", "To confirm", 
        "Too many", "Too much", "Me too",
        "Two days", "Two options", "Two people",
        
        # Other frequently confused pairs in your domain
        "Right number", "Write it down",
        "Send the email", "Sent the email",
        "Buy the product", "By the way",
        "Mail it to me", "Male customer"
    ]

# Email-related phrases and symbols
EMAIL_DOMAINS = [
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com", 
    "icloud.com", "aol.com", "protonmail.com", "mail.com",
    "rogers.com", "bell.net", "sympatico.ca", "ontario.ca",
    "edu.com", "company.com", "business.net", "student.edu"
]

EMAIL_SYMBOLS = [
    "at", "@", "dot", ".", "underscore", "_", "dash", "-",
    "period", ".", "forward slash", "/", "backslash", "\\"
]

# Phonetic spelling contexts
PHONETIC_SPELLING = [
    "a for alpha", " b for bravo", "c for charlie", "d for delta", "e for echo", "f for foxtrot",
    "g for golf", "h for hotel", "i for india", "j for juliet", "k for kilo", "l for lima", "m for mike",
    "n for november", "o for oscar", "p for papa", "q for quebec", "r for romeo", "s for sierra",
    "t for tango", "u for uniform", "v for victor", "w for whiskey", "x for xray", "y for yankee", "z for zulu"
]

PHONETIC_SPELLING_EXPANDED = PHONETIC_SPELLING + [
    # Common letter-word associations
    "a as in apple", "b as in boy", "c as in cat", "d as in dog",
    "e as in echo", "f as in frank", "g as in girl", "h as in house",
    "i as in india", "j as in john", "k as in king", "l as in lion",
    "m as in mary", "n as in nancy", "o as in oscar", "p as in peter",
    "q as in queen", "r as in robert", "s as in sam", "t as in tom",
    "u as in umbrella", "v as in victor", "w as in william", "x as in x-ray",
    "y as in yellow", "z as in zebra",
    "a alpha", "b bravo", "c charlie", "d delta", "e echo", "f foxtrot",
    "g golf", "h hotel", "i india", "j juliet", "k kilo", "l lima", "m mike",
    "n november", "o oscar", "p papa", "q quebec", "r romeo", "s sierra",
    "t tango", "u uniform", "v victor", "v victory", "w whiskey", "x xray", 
    "y yankee", "z zulu",
    # With "for" instead of "as in"
    "a for apple", "b for boy", "c for cat", "d for dog",
    # With "like" 
    "a like apple", "b like boy", "c like cat", "d like dog",
    "a as in alpha"
]

# Name-related contexts
NAME_RESPONSES = [
    "my name is", "this is", "i am", "speaking", "it's", "it is",
    "first name", "last name", "full name", "given name", "family name",
    "that's me", "that's right", "that's my name", "that's not my name",
    "you can call me", "i go by", "people call me", "i'm known as",
    "my first name is", "my last name is", "i spell my name", 
    "that's spelled", "spelled like", "spelled as",
    "as in", "like in", "as for", "for as in", "like for"
]

NAME_PREFIXES_SUFFIXES = [
    "mr", "mrs", "ms", "miss", "dr", "prof", "reverend", "rev",
    "junior", "senior", "jr", "sr", "the second", "the third", 
    "ii", "iii", "iv", "van", "von", "de", "la", "el", "al", "bin",
    "mac", "mc", "o'", "saint", "st", "san"
]

# Lists of common names to improve recognition
COMMON_FIRST_NAMES = [
    "john", "jonathan", "johnny", "james", "jim", "jimmy", "robert", "rob", "bob", "bobby",
    "michael", "mike", "david", "dave", "richard", "rick", "dick", "william", "will", "bill", "billy",
    "thomas", "tom", "tommy", "joseph", "joe", "joey", "charles", "charlie", "chuck",
    "emily", "emma", "olivia", "sophia", "ava", "isabella", "mia", "charlotte", "amelia",
    "elizabeth", "liz", "beth", "eliza", "abigail", "abby", "catherine", "cathy", "kathy",
    "katherine", "kate", "katie", "jennifer", "jen", "jenny", "jessica", "jess", "jessie",
    "mary", "maria", "marie", "sarah", "sara", "madison", "maddy", "samantha", "sam",
    "victoria", "vicky", "vicki", "hannah", "anna", "matthew", "matt", "matty",
    "daniel", "dan", "danny", "christopher", "chris", "andrew", "andy", "drew",
    "joshua", "josh", "anthony", "tony", "justin", "mark", "patrick", "pat",
    "jack", "jackson", "jacob", "jake", "ryan", "tyler", "brandon"
    "nicholas", "nick", "nicky", "benjamin", "ben", "bennie", "samuel", "sam", "sammy",
    "aiden", "jayden", "ethan", "noah", "liam", "lucas", "logan", "mason", "alexander", "alex", 
    "nael", "nyle", "nial", "nayel", "shahzaib"
]

COMMON_LAST_NAMES = [
    "smith", "johnson", "williams", "jones", "brown", "davis", "miller", "wilson", "moore",
    "taylor", "anderson", "thomas", "jackson", "white", "harris", "martin", "thompson",
    "garcia", "martinez", "robinson", "clark", "rodriguez", "lewis", "lee", "walker",
    "hall", "allen", "young", "hernandez", "king", "wright", "lopez", "hill", "scott",
    "green", "adams", "baker", "gonzalez", "nelson", "carter", "mitchell", "perez",
    "roberts", "turner", "phillips", "campbell", "parker", "evans", "edwards", "collins",
    "stewart", "sanchez", "morris", "rogers", "reed", "cook", "morgan", "bell", "murphy",
    "patel", "singh", "kaur", "shah", "khan", "chen", "zhang", "wong", "li", "wang",
    "kim", "park", "choi", "lee", "nguyen", "tran", "diaz", "reyes", "fernandez",
    "jackson", "kumar", "gupta", "sharma", "mehta", "chopra", "chang", "yang"
]

# Contact information phrases and patterns
EMAIL_RESPONSES = [
    "my email is", "my email address is", "you can reach me at",
    "you can email me at", "send it to", "it's", "it is",
    "the address is", "the email is", "reach me at",
    "contact me at", "write to me at", "mail me at",
    "my work email", "my personal email", "my business email",
    "company email", "corporate email", "school email",
    "university email", "student email", "i'll spell that",
    "let me spell that for you", "the spelling is"
]

PHONE_RESPONSES = [
    "my number is", "my phone is", "my phone number is", 
    "you can call me at", "reach me at", "contact me at",
    "my cell is", "my mobile is", "my cell number is", 
    "my mobile number is", "my work number is", "my office number is",
    "my home number is", "my direct line is", "extension",
    "area code", "country code", "plus one", "international",
    "six four seven", "four one six", "nine zero five", 
    "six one three", "two two six", "seven zero five",
    "double", "triple", "oh", "zero", "niner", "five", 
    "three", "eight", "seven", "four", "nine", "two", "one", "six",
    "that's not right", "that's wrong", "incorrect", "that's correct"
]

DOUBLED_LETTERS = [
    "double a", "double b", "double c", "double d", "double e",
    "double f", "double g", "double h", "double i", "double j",
    "double k", "double l", "double m", "double n", "double o",
    "double p", "double q", "double r", "double s", "double t",
    "double u", "double v", "double w", "double x", "double y",
    "double z", "triple a", "triple e", "triple l", "triple m",
    "triple n", "triple o", "triple p", "triple r", "triple s"
]

# Real estate professional information phrases
REALTOR_RESPONSES = [
    "i work with", "i'm with", "i am with", "my realtor is", 
    "working with", "referred by", "recommended by", "my agent is",
    "real estate agent", "realtor", "broker", "sales representative",
    "brokerage", "real estate office", "realty", "real estate company",
    "i'm a", "i am a", "first time buyer", "investor", "seller",
    "homeowner", "tenant", "landlord", "property owner",
    "looking to buy", "looking to sell", "looking to rent",
    "relocating", "moving", "upgrading", "downsizing"
]

# Major real estate brokerages in Ontario
REAL_ESTATE_COMPANIES = [
    "Royal LePage", "RE/MAX", "Century 21", "Coldwell Banker",
    "Keller Williams", "Sutton Group", "HomeLife", "Chestnut Park",
    "Sotheby's International", "Right at Home", "Bosley Real Estate",
    "The Red Pin", "Forest Hill Real Estate", "iPro Realty",
    "Realty One", "Realty Executives", "Exit Realty", "ReMax Integra"
]

# Call context and purpose phrases
CALL_PURPOSE_RESPONSES = [
    "i'm calling about", "i am calling about", "i'd like to know about",
    "interested in", "looking for", "need information about", 
    "want to learn more about", "curious about", "heard about",
    "read about", "saw your", "found your", "recommended",
    "need help with", "having questions about", "question about",
    "inquiry about", "information about", "details about",
    "price of", "cost of", "availability of", "purchase", "buy",
    "sell", "list my property", "market evaluation", "home value",
    "get a quote", "market analysis", "property search", "house hunting",
    "investment property", "rental property", "property management",
    "follow up", "following up", "callback", "call back",
    "meeting", "appointment", "consultation", "viewing", "showing",
    "open house", "private showing", "realtor", "real estate agent",
    "mortgage broker", "home inspector", "appraiser", "lawyer",
    "first time buyer", "upgrading", "downsizing", "relocating",
    "moving", "timeline", "pre-approval", "financing", "budget"
]

# Confirmation, spelling and verification phrases
CONFIRMATION_RESPONSES = [
    "yes", "yeah", "yep", "yup", "sure", "correct", "right", 
    "exactly", "absolutely", "definitely", "precisely",
    "that's it", "that's right", "that's correct", "that is correct",
    "you got it", "spot on", "perfect", "good", "sounds good",
    "looks good", "that works", "fine", "alright", "all right",
    "okay", "ok", "sounds right", "that'd be great", "that would be great",
    "no", "nope", "no way", "not at all", "incorrect", 
    "that's wrong", "that's not right", "that is not right",
    "that's not correct", "that is not correct", "not exactly",
    "not quite", "missing something", "you missed", "mistake"
]

SPELLING_RESPONSES = [
    "yes that's correct", "yes that's right", "yes that is correct", 
    "no that's wrong", "no that's not right", "no that's incorrect",
    "you missed", "you got it wrong", "let me spell it again",
    "i'll spell it again", "let me try again", "one more time",
    "it's not", "it is not", "actually it's", "actually it is",
    "you misunderstood", "let me clarify", "to clarify",
    "the correct spelling is", "it should be", "it's spelled",
    "capital", "lowercase", "upper case", "lower case",
    "big", "small", "letter", "digit", "number",
    "underscore", "hyphen", "dash"
]

LETTER_POSITION_CONTEXTS = [
    "first letter is", "second letter is", "third letter is", "fourth letter is",
    "fifth letter is", "last letter is", "next letter is", "after that is",
    "starts with", "begins with", "ends with"
]

# Domain-specific real estate terminology 
REAL_ESTATE_TERMS = [
    "property", "properties", "real estate", "realtor", "agent", 
    "listing", "listings", "home", "house", "condo", "townhouse",
    "detached", "semi-detached", "apartment", "basement", "finished basement",
    "bedrooms", "bathrooms", "parking", "garage", "driveway",
    "square feet", "sqft", "lot size", "mortgage", "pre-approval", "pre-approved",
    "budget", "price range", "down payment", "closing", "possession",
    "inspection", "appraisal", "market value", "asking price", "offer",
    "multiple offers", "bidding war", "seller", "buyer", "investment",
    "rental", "rent", "lease", "tenant", "landlord", "property management",
    "mls", "commission", "features", "amenities", "neighborhood", "location",
    "schools", "transit", "shopping", "parks", "recreation", "utilities"
]

# Less important contexts with lower boosts
CLOSING_RESPONSES = [
    "thank you", "thanks", "appreciate it", "great", "excellent",
    "perfect", "sounds good", "that's all", "that is all", 
    "nothing else", "no other questions", "no further questions",
    "that's it for now", "that should do it", "that covers it",
    "looking forward", "talk to you soon", "speak to you soon",
    "hear from you soon", "contact me", "reach out", "follow up",
    "have a good day", "have a great day", "have a nice day",
    "goodbye", "bye", "bye bye", "see you", "talk soon"
]

FILLER_WORDS = [
    "um", "uh", "uhm", "er", "ah", "like", "you know", "well", "so", 
    "basically", "actually", "literally", "honestly", "seriously",
    "frankly", "simply", "just", "kind of", "sort of", "type of",
    "okay so", "right so", "anyway", "anyhow", "in any case",
    "i mean", "you see", "let's see", "how can i say", "how do i say",
    "what's the word", "what's it called", "what do you call it",
    "let me think", "give me a second", "one moment", "hang on",
    "hold on", "sorry", "excuse me", "pardon me"
]

# Ontario cities and areas
ONTARIO_CITIES = [
    "Toronto", "Mississauga", "Brampton", "Hamilton", "London", "Markham",
    "Vaughan", "Kitchener", "Windsor", "Richmond Hill", "Oakville", "Burlington",
    "Greater Sudbury", "Oshawa", "Barrie", "St. Catharines", "Cambridge",
    "Kingston", "Whitby", "Guelph", "Thunder Bay", "Waterloo", "Brantford",
    "Pickering", "Niagara Falls", "Peterborough", "Sault Ste. Marie",
    "North York", "Scarborough", "Etobicoke", "York", "East York",
    "Milton", "Halton Hills", "Georgetown", "Acton", "Burlington",
    "Ajax", "Clarington", "Bowmanville", "Courtice", "Newcastle",
    "King City", "Aurora", "Newmarket", "Bradford", "Georgina",
    "Caledon", "Bolton", "Orangeville", "Shelburne", "Alliston",
    "Collingwood", "Wasaga Beach", "Blue Mountain", "Muskoka",
    "Gravenhurst", "Bracebridge", "Huntsville", "Parry Sound"
]

# Property types and features
PROPERTY_TYPES_FEATURES = [
    "detached house", "semi-detached", "townhouse", "condo townhouse",
    "condominium", "apartment", "duplex", "triplex", "fourplex",
    "bungalow", "two-storey", "three-storey", "split-level", "raised ranch",
    "executive home", "luxury home", "starter home", "family home",
    "one bedroom", "two bedroom", "three bedroom", "four bedroom", "five bedroom",
    "one bathroom", "two bathroom", "three bathroom", "powder room", "ensuite",
    "master bedroom", "master suite", "walk-in closet", "main floor",
    "upper level", "lower level", "basement apartment", "in-law suite",
    "hardwood floors", "ceramic tile", "carpet", "laminate", "vinyl",
    "granite counters", "quartz counters", "stainless steel appliances",
    "updated kitchen", "modern kitchen", "eat-in kitchen", "breakfast nook",
    "formal dining room", "living room", "family room", "great room",
    "den", "office", "study", "recreation room", "media room", "gym",
    "laundry room", "mudroom", "pantry", "storage", "attic", "crawl space",
    "attached garage", "detached garage", "carport", "parking pad",
    "single car garage", "double car garage", "triple car garage",
    "visitor parking", "underground parking", "surface parking",
    "fenced yard", "landscaped", "mature trees", "deck", "patio",
    "balcony", "pool", "hot tub", "shed", "workshop"
]

contextual_ngrams = [
        # Email context n-grams
        "my email is", "send it to my email", "email address is", 
        "spelled like", "that's spelled", 
        
        # Confirmation context n-grams
        "no that's not right", "no that's incorrect", 
        "I know that", "I don't know", 
        
        # Location context n-grams
        "over there", "located there", "go there",
        "their office", "their company", "their business",
        
        # Quantity context n-grams
        "too many", "too much", "too late",
        "to the", "to my", "to our", 
        "two of them", "two people", "two days"
]


# Define the standard boost levels
class BoostLevel:
    """Standard boost levels for speech contexts"""
    VERY_LOW = 0.01
    LOW = 0.1       # For contexts to be de-emphasized 
    MEDIUM = 10.0   # Basic contextual information
    HIGH = 15.0     # Important contextual information
    VERY_HIGH = 20.0 # Critical recognition contexts
    ULTRA_HIGH = 30.0 # Highest priority contexts

def create_base_speech_contexts():
    """Create the base set of speech contexts with appropriate boosts."""
    return [
        # Critical for accurate recognition
        speech.SpeechContext(phrases=INDIVIDUAL_LETTERS, boost=BoostLevel.VERY_HIGH), 
        speech.SpeechContext(phrases=PHONETIC_SPELLING_EXPANDED, boost=BoostLevel.VERY_HIGH),
        speech.SpeechContext(phrases=CONFIRMATION_RESPONSES, boost=BoostLevel.HIGH),
        speech.SpeechContext(phrases=SPELLING_RESPONSES, boost=BoostLevel.HIGH),
        
        # Important for collecting contact information
        speech.SpeechContext(phrases=EMAIL_SYMBOLS, boost=BoostLevel.HIGH),
        speech.SpeechContext(phrases=EMAIL_DOMAINS, boost=BoostLevel.HIGH),
        speech.SpeechContext(phrases=EMAIL_RESPONSES, boost=BoostLevel.HIGH),
        speech.SpeechContext(phrases=PHONE_RESPONSES, boost=BoostLevel.HIGH),
        
        # Important for name collection
        speech.SpeechContext(phrases=NAME_RESPONSES, boost=BoostLevel.HIGH),
        speech.SpeechContext(phrases=COMMON_FIRST_NAMES, boost=BoostLevel.HIGH),
        speech.SpeechContext(phrases=COMMON_LAST_NAMES, boost=BoostLevel.HIGH),
        speech.SpeechContext(phrases=NAME_PREFIXES_SUFFIXES, boost=BoostLevel.MEDIUM),
        
        # Important for real estate discussion
        speech.SpeechContext(phrases=REAL_ESTATE_TERMS, boost=BoostLevel.HIGH),
        speech.SpeechContext(phrases=ONTARIO_CITIES, boost=BoostLevel.HIGH),
        speech.SpeechContext(phrases=PROPERTY_TYPES_FEATURES, boost=BoostLevel.HIGH),
        speech.SpeechContext(phrases=CALL_PURPOSE_RESPONSES, boost=BoostLevel.MEDIUM),
        speech.SpeechContext(phrases=REALTOR_RESPONSES, boost=BoostLevel.MEDIUM),
        speech.SpeechContext(phrases=REAL_ESTATE_COMPANIES, boost=BoostLevel.MEDIUM),
        
        # Less critical contexts
        speech.SpeechContext(phrases=CLOSING_RESPONSES, boost=BoostLevel.MEDIUM),
        
        # De-emphasized contexts
        speech.SpeechContext(phrases=FILLER_WORDS, boost=BoostLevel.LOW),

        speech.SpeechContext(phrases=confused_words, boost=BoostLevel.MEDIUM),
        
        speech.SpeechContext(phrases=context_disambiguated_phrases, boost=BoostLevel.MEDIUM),

        speech.SpeechContext(phrases=contextual_ngrams, boost=BoostLevel.MEDIUM),

        speech.SpeechContext(phrases=ONTARIO_CITIES, boost=BoostLevel.VERY_HIGH),
        speech.SpeechContext(phrases=PROPERTY_TYPES_FEATURES, boost=BoostLevel.VERY_HIGH)

    ]

def create_spelling_mode_contexts(spelling_type=None):
    """Create optimized contexts for spelling mode."""
    if spelling_type == "name_collection":
        return [
            speech.SpeechContext(phrases=INDIVIDUAL_LETTERS, boost=BoostLevel.VERY_HIGH),
            speech.SpeechContext(phrases=COMMON_FIRST_NAMES, boost=BoostLevel.VERY_HIGH),
            speech.SpeechContext(phrases=COMMON_LAST_NAMES, boost=BoostLevel.VERY_HIGH),
            speech.SpeechContext(phrases=PHONETIC_SPELLING_EXPANDED, boost=BoostLevel.VERY_HIGH),
            speech.SpeechContext(phrases=CONFIRMATION_RESPONSES, boost=BoostLevel.VERY_HIGH),
            speech.SpeechContext(phrases=SPELLING_RESPONSES, boost=BoostLevel.HIGH),
            speech.SpeechContext(phrases=NAME_PREFIXES_SUFFIXES, boost=BoostLevel.HIGH),
            speech.SpeechContext(phrases=FILLER_WORDS, boost=BoostLevel.VERY_LOW)

        ]
    elif spelling_type == "email":
        return [
            speech.SpeechContext(phrases=INDIVIDUAL_LETTERS, boost=BoostLevel.ULTRA_HIGH),
            speech.SpeechContext(phrases=EMAIL_SYMBOLS, boost=BoostLevel.ULTRA_HIGH),
            speech.SpeechContext(phrases=EMAIL_DOMAINS, boost=BoostLevel.VERY_HIGH),
            speech.SpeechContext(phrases=CONFUSED_LETTER_PAIRS, boost=BoostLevel.VERY_HIGH),
            speech.SpeechContext(phrases=CONFIRMATION_RESPONSES, boost=BoostLevel.VERY_HIGH),
            speech.SpeechContext(phrases=PHONETIC_SPELLING_EXPANDED, boost=BoostLevel.VERY_HIGH),
            speech.SpeechContext(phrases=DOUBLED_LETTERS, boost=BoostLevel.VERY_HIGH),
            speech.SpeechContext(phrases=SPELLING_RESPONSES, boost=BoostLevel.VERY_HIGH),
            speech.SpeechContext(phrases=FILLER_WORDS, boost=BoostLevel.VERY_LOW)

        ]
    elif spelling_type == "phone":
        return [
            speech.SpeechContext(phrases=INDIVIDUAL_LETTERS, boost=BoostLevel.VERY_HIGH),
            speech.SpeechContext(phrases=PHONE_RESPONSES, boost=BoostLevel.VERY_HIGH),
            speech.SpeechContext(phrases=CONFIRMATION_RESPONSES, boost=BoostLevel.VERY_HIGH),
            speech.SpeechContext(phrases=DOUBLED_LETTERS, boost=BoostLevel.HIGH),
        ]
    else:
        # Default spelling mode (names, etc.)
        return [
            speech.SpeechContext(phrases=INDIVIDUAL_LETTERS, boost=BoostLevel.ULTRA_HIGH),
            speech.SpeechContext(phrases=CONFUSED_LETTER_PAIRS, boost=BoostLevel.VERY_HIGH),
            speech.SpeechContext(phrases=LETTER_POSITION_CONTEXTS, boost=BoostLevel.VERY_HIGH),
            speech.SpeechContext(phrases=PHONETIC_SPELLING, boost=BoostLevel.VERY_HIGH),
            speech.SpeechContext(phrases=PHONETIC_SPELLING_EXPANDED, boost=BoostLevel.ULTRA_HIGH),
            speech.SpeechContext(phrases=CONFIRMATION_RESPONSES, boost=BoostLevel.VERY_HIGH),
            speech.SpeechContext(phrases=SPELLING_RESPONSES, boost=BoostLevel.VERY_HIGH),
            speech.SpeechContext(phrases=DOUBLED_LETTERS, boost=BoostLevel.VERY_HIGH),
            speech.SpeechContext(phrases=FILLER_WORDS, boost=BoostLevel.VERY_LOW)

        ]

def create_assistance_mode_contexts():
    """Create optimized contexts for assistance mode."""
    return [
        speech.SpeechContext(phrases=REAL_ESTATE_TERMS, boost=BoostLevel.ULTRA_HIGH),
        speech.SpeechContext(phrases=ONTARIO_CITIES, boost=BoostLevel.ULTRA_HIGH),
        speech.SpeechContext(phrases=PROPERTY_TYPES_FEATURES, boost=BoostLevel.ULTRA_HIGH),
        speech.SpeechContext(phrases=CONFIRMATION_RESPONSES, boost=BoostLevel.HIGH),
        speech.SpeechContext(phrases=CALL_PURPOSE_RESPONSES, boost=BoostLevel.VERY_HIGH),
        speech.SpeechContext(phrases=INDIVIDUAL_LETTERS, boost=BoostLevel.HIGH),
        speech.SpeechContext(phrases=confused_words, boost=BoostLevel.MEDIUM),
        speech.SpeechContext(phrases=context_disambiguated_phrases, boost=BoostLevel.MEDIUM),
        speech.SpeechContext(phrases=contextual_ngrams, boost=BoostLevel.MEDIUM)
    ]

def create_first_response_contexts():
    """Create optimized contexts for first response mode."""
    return [
        speech.SpeechContext(phrases=REAL_ESTATE_TERMS, boost=BoostLevel.ULTRA_HIGH),
        speech.SpeechContext(phrases=ONTARIO_CITIES, boost=BoostLevel.VERY_HIGH),
        speech.SpeechContext(phrases=PROPERTY_TYPES_FEATURES, boost=BoostLevel.VERY_HIGH),
        speech.SpeechContext(phrases=CALL_PURPOSE_RESPONSES, boost=BoostLevel.VERY_HIGH),
        speech.SpeechContext(phrases=REALTOR_RESPONSES, boost=BoostLevel.HIGH),
        speech.SpeechContext(phrases=REAL_ESTATE_COMPANIES, boost=BoostLevel.HIGH),
        speech.SpeechContext(phrases=INDIVIDUAL_LETTERS, boost=BoostLevel.HIGH),
        speech.SpeechContext(phrases=CONFIRMATION_RESPONSES, boost=BoostLevel.HIGH),
    ]
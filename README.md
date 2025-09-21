# AIVA - AI Voice Agent

## Introduction

AIVA is an AI voice agent that automates inbound and outbound calls, simulating real-like voice speech using text-to-speech models and state-of-the-art LLMs for response generation to user queries. AIVA has been used to handle inbound inquiries for spectrometer companies and decrease speed to lead for real estate agents by gathering lead preferences etc. 

The system integrates with popular CRM platforms (FollowUpBoss, HubSpot, Zoho), uses Twilio for voice services, and leverages Google's speech recognition along with multiple TTS providers (ElevenLabs, Google, Cartesia) to deliver human-like conversational experiences.

## Implementation Guide

### Step 1: Clone the Repository

```bash
git clone https://github.com/naellakhani/ai-voice-assistant.git
cd ai-voice-assistant
```

### Step 2: Set Up Google Credentials

Create a `credentials` folder in the ai-voice-assistant folder and obtain Google service account credentials for both Speech-to-Text and Text-to-Speech services.

```bash
mkdir credentials
```

#### Obtaining Google Cloud Credentials:

1. **Create a Google Cloud Project**
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project

2. **Enable Required APIs**
   - Navigate to APIs & Services → Library
   - Search for "Google Cloud Text-to-Speech API" and enable it
   - Search for "Google Cloud Speech-to-Text API" and enable it

3. **Create Service Account**
   - Go to IAM & Admin → Service Accounts
   - Click "Create Service Account"
   - Fill in the service account details

4. **Generate JSON Key**
   - Click on your newly created service account
   - Go to the "Keys" tab
   - Click "Add Key" → "Create new key"
   - Choose JSON format and download

5. **Add Credentials to Project**
   - Place the downloaded JSON file in the `credentials` folder
   - Update your `.env.docker` file with the credential paths:
   ```
   GOOGLE_APPLICATION_CREDENTIALS_SPEECH=/app/credentials/[your-speech-credentials-file].json
   GOOGLE_APPLICATION_CREDENTIALS_TEXT=/app/credentials/[your-text-credentials-file].json
   ```
> **Note**: You can use the same JSON file for both speech and text services, or create separate service accounts for each.

### Step 3: Configure Twilio Credentials

Get your Twilio credentials from the [Twilio Console](https://console.twilio.com/) and add them to your `.env.docker` file:

```
TWILIO_ACCOUNT_SID=your-account-sid-here
TWILIO_AUTH_TOKEN=your-auth-token-here
TWILIO_FROM_NUMBER=+1234567890
```

The Account SID and Auth Token are available on your Twilio dashboard, and the from number is your registered Twilio phone number.

### Step 4: Configure TTS Providers (Optional)

If you want to use ElevenLabs or Cartesia for enhanced voice synthesis, obtain their API keys and voice IDs (which can be cloned voices) and add them to your `.env.docker` file:

```
TTS_PROVIDER=elevenlabs
ELEVENLABS_API_KEY=your-elevenlabs-api-key
ELEVENLABS_VOICE_ID=your-voice-id

# OR for Cartesia
TTS_PROVIDER=cartesia
CARTESIA_API_KEY=your-cartesia-api-key
CARTESIA_VOICE_ID=your-cartesia-voice-id
```

### Step 5: Configure Database

For Docker Compose deployment, database connection is handled automatically - just set `DB_PASSWORD` in your `.env.docker` file. For local development, set up your own PostgreSQL database and create the full `DATABASE_URL` in your `.env.docker` file.

### Step 6: Configure Ngrok

Get your Ngrok auth token from [ngrok.com](https://ngrok.com/) and add it to your `.env.docker` file:

```
NGROK_AUTH_TOKEN=your-ngrok-auth-token
```

### Step 7: Configure CRM Integration (Optional)

CRM integration can be controlled with `CRM_ENABLED=true/false` in your `.env.docker` file.

#### FollowUpBoss Integration
1. Register your system at [FollowUpBoss System Registration](https://apps.followupboss.com/system-registration)
2. In your FollowUpBoss admin panel, get your API key
3. Add to your `.env.docker` file:
```
CRM_ENABLED=true
PRIMARY_CRM=followupboss
FOLLOWUPBOSS_API_KEY=your-api-key
FOLLOWUPBOSS_X_SYSTEM=your-system-identifier
FOLLOWUPBOSS_X_SYSTEM_KEY=your-system-key
```

### Step 8: Configure Email Notifications (Optional)

To receive email notifications about call events, fill in your SMTP configuration in the `.env.docker` file:

```
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-app-password
SMTP_FROM_EMAIL=your-email@gmail.com
SMTP_TO_EMAIL=notifications@yourdomain.com
```

### Step 9: Run the Application

Navigate to the Docker deployment folder and start the application:

```bash
cd realtor-dashboard-backend/ai-voice-assistant/docker-deployment
docker-compose up
```

The application will be available at `http://localhost:5000` and your Ngrok tunnel URL will be displayed in the console.
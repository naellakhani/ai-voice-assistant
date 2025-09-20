# API Documentation

## Leads

### GET /api/leads
Retrieves a list of leads with pagination, search, and filtering options.

Query Parameters:
- `page` (optional): Page number for pagination (default: 1)
- `limit` (optional): Number of items per page (default: 10)
- `search` (optional): Search query for name, email, or phone
- `email` (optional): Filter by email
- `name` (optional): Filter by name
- `phone` (optional): Filter by phone

Response:
```json
{
  "leads": [...],
  "currentPage": number,
  "totalPages": number,
  "totalItems": number
}
```

### GET /api/leads/:id
Retrieves a specific lead by ID and its associated call history.

Parameters:
- `id`: Lead ID

Response:
```json
{
  "lead": {...},
  "callHistory": [...]
}
```

### POST /api/leads
Creates a new lead.

Request Body:
```json
{
  "name": "string",
  "email": "string",
  "phone": "string"
}
```

Response: The created lead object

## Call History

### GET /api/call-history
Retrieves call history with pagination, search, and filtering options.

Query Parameters:
- `page` (optional): Page number for pagination (default: 1)
- `limit` (optional): Number of items per page (default: 10)
- `search` (optional): Search query for email, realtor, or property_type
- `email` (optional): Filter by email
- `realtor` (optional): Filter by realtor
- `property_type` (optional): Filter by property type

Response:
```json
{
  "callHistory": [...],
  "currentPage": number,
  "totalPages": number,
  "totalItems": number
}
```
# Bot Fight AI

Bot Fight AI is a backend project for creating an AI player for Bot Fight Online. The goal is for the AI to receive information about a match, generate valid programs, test possible programs, and choose one to play.

Right now, the project is in an early testing stage. It includes a small FastAPI application that connects to a local Ollama model and asks it to generate structured JSON responses. It is not yet connected to the real game, a simulator, or a database.

The current work is focused on confirming that the application can communicate with a local language model before adding the full game integration and evaluation system.

# Virtual Staff - RAG for Healthcare System

## Introduction

This project implements a Retrieval-Augmented Generation (RAG) system designed to simulate a virtual hospital staff assistant.

The system is capable of:

* Understanding patient symptoms
* Asking follow-up questions
* Retrieving relevant medical information from a vector database
* Suggesting appropriate hospital departments

The project is designed to run fully locally using a lightweight language model.

---

## Tech Stack

* Python
* Qdrant (Vector Database)
* LangChain
* Ollama (Local LLM Runtime)
* Qwen2.5:3B (Local Language Model)

---

## Project Structure

```id="f2m8xk"
.
├── virtual_staff_brain.py
├── virtual_staff_brain_2_0.py
├── virtual_staff_brain_3_0.py
├── data_pipeline.py
├── database_pipeline.py
├── qdrant_ingest.py
├── qdrant_demo.py
├── requirements.txt
├── .env.example
```

---

## Installation

### 1. Clone repository

```id="zvwr5q"
git clone https://github.com/ntnquang2906/DigitalTwinforHealthcareSystem.git
cd DigitalTwinforHealthcareSystem
```

### 2. Create virtual environment

```id="r7l9xm"
python -m venv venv
venv\Scripts\activate
```

### 3. Install dependencies

```id="k9r2yt"
pip install -r requirements.txt
```

---

## Running Local LLM (Qwen2.5)

### 1. Install Ollama

Download and install Ollama from its official website.

### 2. Pull the model

```id="c3s8we"
ollama pull qwen2.5:3b
```

### 3. Test the model

```id="d8k1pl"
ollama run qwen2.5:3b
```

---

## Environment Setup

Create a `.env` file based on `.env.example` if needed.

Example:

```id="x7v2nb"
API_KEY=your_api_key
```

---

## Usage

Run the main system:

```id="q4p1zx"
python virtual_staff_brain_3_0.py
livekit_kiosk.py
update_kiosk.py
```

---

## How It Works

1. User inputs symptoms
2. The system asks follow-up questions
3. Relevant data is retrieved from Qdrant
4. The local LLM generates responses and recommendations

---

## Features

* Symptom understanding
* Context-aware questioning
* Retrieval-Augmented Generation (RAG) pipeline
* Local LLM inference using Qwen2.5
* Modular and extensible architecture

---

## Notes

* Do not upload `.env` file
* Local vector database is not included in the repository
* Ollama must be running before executing the system

---

## Author
*Nguyen Dinh Phien

FROM python:3.8

# Init
WORKDIR /app
RUN addgroup --system app && adduser --system --group app

# Install Requirments
RUN apt-get -y update && apt-get install -y telnet iputils-ping
COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt

# Copy Files
COPY ./core/master_scheduler.py ./master_scheduler.py
COPY ./core/db_data_loader_basketball.py ./db_data_loader_basketball.py
COPY ./core/db_data_loader_football.py ./db_data_loader_football.py

# Set User
USER app
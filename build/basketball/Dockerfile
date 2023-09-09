FROM registry.oddsbender.com/oddsbender/selenium-driver:latest

# Init
WORKDIR /app
RUN addgroup --system app && adduser --system --group app

# Install Requirments
RUN apt-get -y update && apt-get install -y telnet iputils-ping
COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt

#Copy Configuration
COPY ./basketball/conf/ ./conf/

#Copy Scrapers
COPY ./basketball/utilities/ ./utilities/
COPY ./basketball/*.py  ./

# Set User
USER app
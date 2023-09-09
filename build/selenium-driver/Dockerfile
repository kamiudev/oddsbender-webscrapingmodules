FROM python:3.8

# # install google chrome
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add -
RUN sh -c 'echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list'
RUN apt-get -y update
RUN apt-get install -yqq google-chrome-stable

# install firefox
ARG FIREFOX_VERSION=107.0
RUN wget --no-verbose -O /tmp/firefox.tar.bz2 https://download-installer.cdn.mozilla.net/pub/firefox/releases/$FIREFOX_VERSION/linux-x86_64/en-US/firefox-$FIREFOX_VERSION.tar.bz2 \
	&& tar -xf /tmp/firefox.tar.bz2 --directory /opt \
	&& rm /tmp/firefox.tar.bz2 \
	&& mv /opt/firefox /opt/firefox-${FIREFOX_VERSION} \
	&& ln -fs /opt/firefox-${FIREFOX_VERSION}/firefox /usr/bin/firefox
RUN apt-get update && apt-get install -y wget bzip2 libxtst6 libgtk-3-0 libx11-xcb-dev libdbus-glib-1-2 libxt6 libpci-dev && rm -rf /var/lib/apt/lists/*

# Install Firefox Driver
ARG GECKO_DRIVER_VERSION=0.32.0
RUN wget -O /tmp/geckodriver.tar.gz https://github.com/mozilla/geckodriver/releases/download/v${GECKO_DRIVER_VERSION}/geckodriver-v${GECKO_DRIVER_VERSION}-linux64.tar.gz \
  && tar -xzf /tmp/geckodriver.tar.gz --directory /opt \
	&& rm /tmp/geckodriver.tar.gz \
	&& ln -fs /opt/geckodriver /usr/bin/geckodriver

WORKDIR /app

# install chromedriver
RUN apt-get -y update && apt-get install -yqq unzip vim
RUN wget -O /tmp/chromedriver.zip http://chromedriver.storage.googleapis.com/`curl -sS chromedriver.storage.googleapis.com/LATEST_RELEASE`/chromedriver_linux64.zip
RUN unzip /tmp/chromedriver.zip chromedriver -d /usr/local/bin/

# set display port to avoid crash
ENV DISPLAY=:99

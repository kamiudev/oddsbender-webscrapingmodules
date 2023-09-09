## Installation guide

*Note: The module was created with Python 3.8.Before you begin, make sure that the Python package is available on your computer*

1. Clone the repository from Bitbucket.

2. Go to the root of the repository.

3. Run inside your terminal: <br> 
`pip install -r requirements.txt` <br> 
*Note: You need to be in the directory with the requrements.txt file* <br> 

4. Go to the â€œconfâ€ folder

5. Open sportsbok â€œ*.confâ€ file. Update the values of the variables "browser_*", "wodule_work_duration" and "update_frequency" in format, provided as in the example. 
	These variables have the default values.

6. Open logging.conf, check that the server address and token contains the correct url and token in args (https://app.logz.io/#/dashboard/send-your-data/log-sources/python) <br> 
*Note: Each script contains a DEBUG_FLAG developer parameter, when set to 0, the logs are written to logz.io, else, at parameter 1, the log is written in the /log dir and in stdouth

7. Run the required script to get started
<br> 
<br> 
After the execution of the script, in the module directory will appear csv folder with files.

## Launch from one script <br> 
1. Start redis DB <br> 
`sudo service redis-server start` <br> 

2. Execute the script <br> 
`./start_scrapers.sh <args>` <br> 
This script will run necessary scripts if they have not been started before. <br> 

*For example:* <br> 
`./start_scrapers.sh betmgm` will start: **betmgm_url.py**, **betmgm_popular.py**, **db_data_loader.py**, **master.py**. <br> 

## Game statuses: <br> 
0 - Added to Redis DB (New game) <br> 
1 - prop.py starts working with URL <br> 
2 - The game has ended <br> 
3 - Error, the script has been restarted, proceed working with URL <br> 

## DB's <br> 
db=0 - url <br> 
db=1 - data <br> 

## Create DB Postgres <br> 
`sudo apt-update` <br> 
`sudo apt install postgres postgres-contrlib` <br> 
<br> 
`sudo apt-get install python3-pip` <br> 
`pip3 install psycopg2` <br> 

Another possible option to start if previous option doesn't work: <br> 
`sudo apt install python3-dev libpq-dev` <br> 
`pip3 install psycopg2` <br> 

Service postgresql status: <br> 
`sudo -i -u postgres` <br> 

`psql`<br> 
`CREATE DATABASE bender;`<br> 
`CREATE TABLE IF NOT EXISTS public.sportbooks(id integer NOT NULL GENERATED ALWAYS AS IDENTITY ( INCREMENT 1 START 1 MINVALUE 1 MAXVALUE 9999999 CACHE 1 ), stream_name text COLLATE pg_catalog."default", time_stamp text COLLATE pg_catalog."default", json_data text COLLATE pg_catalog."default", sportsbook_name text COLLATE pg_catalog."default", sport_name text COLLATE pg_catalog."default", insert_time timestamp without time zone);
TABLESPACE pg_default;` <br> 
`ALTER TABLE IF EXISTS public.sportbooks OWNER to postgres;` <br> 

## Add Firefox driver to local storage
1. go to https://github.com/mozilla/geckodriver/releases the geckodriver releases page. Find the latest version of the driver for your platform
(for today it is 0.32.0)
2. Download it
wget https://github.com/mozilla/geckodriver/releases/download/v0.32.0/geckodriver-v0.32.0-linux64.tar.gz
3. Extract the file with:
tar -xvzf geckodriver*
4. move file to /usr/local/bin/
cp geckodriver /usr/local/bin/
5. make it executable:
sudo chmod +x /usr/local/bin/geckodriver
6. Add the driver to your PATH so other tools can find it:
export PATH=$PATH:/path-to-extracted-file/.
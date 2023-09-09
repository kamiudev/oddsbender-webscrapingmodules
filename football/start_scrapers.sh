
#!/bin/bash

scraper_type="${SCRAPER_TYPE:-"popular"}"

echo "Attempt to start the script master.py"
if [ `pgrep -a python | grep 'master.py' | grep -v grep | wc -l | tr -d ' \t'` -gt 0 ]; 
	then echo "Script master.py is running"
else python3 master.py > /dev/null 2>&1 & echo "Script master.py started"
fi

echo "Attempt to start the script db_data_loader.py"
if [ `pgrep -a python | grep 'db_data_loader.py' | grep -v grep | wc -l | tr -d ' \t'` -gt 0 ];
        then echo "Script db_data_loader.py is running"
else python3 db_data_loader.py > /dev/null 2>&1 & echo "Script db_data_loader.py started"
fi

echo "Attempt to start the script $1_url.py"
if [ `pgrep -a python | grep $1_url.py | grep -v grep | wc -l | tr -d ' \t'` -gt 0 ];
        then echo "Script $1_url.py is running"
else python3 $1_url.py > /dev/null 2>&1 & echo "Script $1_url.py started"
fi

if [ "$scraper_type" == "popular" ]; then
        echo "Attempt to start the script $1popular.py"
        if [ `pgrep -a python | grep $1popular.py | grep -v grep | wc -l | tr -d ' \t'` -gt 0 ];
                then echo "Script $1popular.py is running"
        else python3 $1popular.py > /dev/null 2>&1 & echo "Script $1popular.py started"
        fi
elif [ "$scraper_type" == "prop" ]; then
        echo "Attempt to start the script $1prop.py"
        if [ `pgrep -a python | grep $1prop.py | grep -v grep | wc -l | tr -d ' \t'` -gt 0 ];
                then echo "Script $1prop.py is running"
        else python3 $1prop.py > /dev/null 2>&1 & echo "Script $1prop.py started"
        fi
fi

tail -f /dev/null

declare -a scraper_deployments
scraper_deployments=(
	"deployment/oddsbender-scrapers-barstool-basketball"
	"deployment/oddsbender-scrapers-barstool-football"
	"deployment/oddsbender-scrapers-betmgm-basketball"
	"deployment/oddsbender-scrapers-betmgm-football"
	"deployment/oddsbender-scrapers-caesars-basketball"
	"deployment/oddsbender-scrapers-caesars-football"
	"deployment/oddsbender-scrapers-draftkings-basketball"
	"deployment/oddsbender-scrapers-draftkings-football"
	"deployment/oddsbender-scrapers-fanduel-basketball"
	"deployment/oddsbender-scrapers-fanduel-football"
	"deployment/oddsbender-scrapers-sugarhouse-basketball"
	"deployment/oddsbender-scrapers-sugarhouse-football"
	"deployment/oddsbender-back-end-compare"
	"deployment/oddsbender-scrapers-betmgm-basketball-prop"
	"deployment/oddsbender-scrapers-betmgm-football-prop"
	"deployment/oddsbender-scrapers-caesars-basketball-prop"
	"deployment/oddsbender-scrapers-caesars-football-prop"
	"deployment/oddsbender-scrapers-draftkings-basketball-prop"
	"deployment/oddsbender-scrapers-draftkings-football-prop"
	"deployment/oddsbender-scrapers-fanduel-basketball-prop"
	"deployment/oddsbender-scrapers-fanduel-football-prop"
	"deployment/oddsbender-scrapers-sugarhouse-basketball-prop"
	"deployment/oddsbender-scrapers-sugarhouse-football-prop"
	"deployment/oddsbender-scrapers-master-scheduler"
	"deployment/oddsbender-scrapers-data-loader"
	"statefulset/oddsbender-scrapers-redis-master"
)

for deployment in ${scraper_deployments[@]}
do
	kubectl scale $deployment --replicas $1 2> /dev/null
done

declare -a scraper_statefulsets

scraper_statefulsets=(
	"statefulset/oddsbender-scrapers-redis-replicas"
	"statefulset/oddsbender-scrapers-rabbitmq"
)
for deployment in ${scraper_statefulsets[@]}
do
	if (($1 > 0));then
		kubectl scale $deployment --replicas 3 2> /dev/null
	else
		kubectl scale $deployment --replicas $1 2> /dev/null
	fi
done
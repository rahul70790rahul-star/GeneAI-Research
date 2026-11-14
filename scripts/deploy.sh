#!/bin/bash
# GeneAI Research - Deployment Script

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
ENVIRONMENT="staging"
ACTION="deploy"
BUILD_IMAGE=true
RUN_TESTS=true
SKIP_BACKUP=false

# Help function
usage() {
    cat << EOF
Usage: $0 [OPTIONS]

GeneAI Research Deployment Script

OPTIONS:
    -e, --environment ENV    Target environment (staging|production) [default: staging]
    -a, --action ACTION      Action to perform (deploy|rollback|backup|restore) [default: deploy]
    --no-build               Skip Docker image build
    --no-tests               Skip pre-deployment tests
    --skip-backup            Skip database backup before deployment
    -h, --help               Show this help message

EXAMPLES:
    $0 -e staging                    # Deploy to staging
    $0 -e production                 # Deploy to production
    $0 -e staging -a rollback        # Rollback staging
    $0 -e production -a backup       # Backup production database
    $0 --no-build --no-tests         # Quick deploy without build/tests

EOF
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -e|--environment)
            ENVIRONMENT="$2"
            shift 2
            ;;
        -a|--action)
            ACTION="$2"
            shift 2
            ;;
        --no-build)
            BUILD_IMAGE=false
            shift
            ;;
        --no-tests)
            RUN_TESTS=false
            shift
            ;;
        --skip-backup)
            SKIP_BACKUP=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            usage
            exit 1
            ;;
    esac
done

# Validate environment
if [[ ! "$ENVIRONMENT" =~ ^(staging|production)$ ]]; then
    echo -e "${RED}Invalid environment: $ENVIRONMENT. Must be 'staging' or 'production'.${NC}"
    exit 1
fi

# Validate action
if [[ ! "$ACTION" =~ ^(deploy|rollback|backup|restore)$ ]]; then
    echo -e "${RED}Invalid action: $ACTION. Must be 'deploy', 'rollback', 'backup', or 'restore'.${NC}"
    exit 1
fi

# Set environment-specific variables
case $ENVIRONMENT in
    staging)
        COMPOSE_FILE="docker-compose.staging.yml"
        ENV_FILE=".env.staging"
        ;;
    production)
        COMPOSE_FILE="docker-compose.production.yml"
        ENV_FILE=".env.production"
        ;;
esac

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}GeneAI Research Deployment${NC}"
echo -e "${BLUE}Environment: ${YELLOW}$ENVIRONMENT${NC}"
echo -e "${BLUE}Action: ${YELLOW}$ACTION${NC}"
echo -e "${BLUE}========================================${NC}"

# Function to run pre-deployment checks
pre_deployment_checks() {
    echo -e "\n${YELLOW}Running pre-deployment checks...${NC}"
    
    # Check if Docker is running
    if ! docker info > /dev/null 2>&1; then
        echo -e "${RED}Docker is not running. Please start Docker.${NC}"
        exit 1
    fi
    
    # Check if compose file exists
    if [[ ! -f "$PROJECT_ROOT/$COMPOSE_FILE" ]]; then
        echo -e "${RED}Compose file not found: $COMPOSE_FILE${NC}"
        exit 1
    fi
    
    # Check if env file exists
    if [[ ! -f "$PROJECT_ROOT/$ENV_FILE" ]]; then
        echo -e "${YELLOW}Warning: Environment file not found: $ENV_FILE${NC}"
        echo -e "${YELLOW}Using default environment variables.${NC}"
    fi
    
    echo -e "${GREEN}Pre-deployment checks passed.${NC}"
}

# Function to run tests
run_tests() {
    if [[ "$RUN_TESTS" == true ]]; then
        echo -e "\n${YELLOW}Running tests...${NC}"
        
        cd "$PROJECT_ROOT"
        
        # Run smoke tests
        echo "Running smoke tests..."
        python -m pytest tests/test_smoke.py -v --tb=short || {
            echo -e "${RED}Smoke tests failed!${NC}"
            exit 1
        }
        
        # Run unit tests
        echo "Running unit tests..."
        python -m pytest tests/ -m "unit" -v --tb=short || {
            echo -e "${RED}Unit tests failed!${NC}"
            exit 1
        }
        
        echo -e "${GREEN}All tests passed.${NC}"
    else
        echo -e "${YELLOW}Skipping tests (--no-tests flag).${NC}"
    fi
}

# Function to build Docker image
build_image() {
    if [[ "$BUILD_IMAGE" == true ]]; then
        echo -e "\n${YELLOW}Building Docker image...${NC}"
        
        cd "$PROJECT_ROOT"
        
        IMAGE_TAG="geneai-research:${ENVIRONMENT}-$(date +%Y%m%d-%H%M%S)"
        
        docker build -t "$IMAGE_TAG" -t "geneai-research:${ENVIRONMENT}-latest" . || {
            echo -e "${RED}Docker build failed!${NC}"
            exit 1
        }
        
        echo -e "${GREEN}Docker image built: $IMAGE_TAG${NC}"
        
        # Export image tag for use in deployment
        export GENEAI_IMAGE_TAG="$IMAGE_TAG"
    else
        echo -e "${YELLOW}Skipping Docker build (--no-build flag).${NC}"
        export GENEAI_IMAGE_TAG="geneai-research:${ENVIRONMENT}-latest"
    fi
}

# Function to backup database
backup_database() {
    if [[ "$SKIP_BACKUP" == false && "$ACTION" == "deploy" ]]; then
        echo -e "\n${YELLOW}Backing up database...${NC}"
        
        BACKUP_DIR="$PROJECT_ROOT/backups/$ENVIRONMENT"
        mkdir -p "$BACKUP_DIR"
        
        BACKUP_FILE="$BACKUP_DIR/geneai_${ENVIRONMENT}_$(date +%Y%m%d_%H%M%S).sql"
        
        # Use docker compose to run pg_dump
        docker compose -f "$PROJECT_ROOT/$COMPOSE_FILE" exec -T postgres pg_dump -U geneai geneai > "$BACKUP_FILE" 2>/dev/null || {
            echo -e "${YELLOW}Warning: Database backup failed (database might not be running).${NC}"
        }
        
        if [[ -f "$BACKUP_FILE" && -s "$BACKUP_FILE" ]]; then
            echo -e "${GREEN}Database backed up to: $BACKUP_FILE${NC}"
            
            # Keep only last 10 backups
            ls -t "$BACKUP_DIR"/geneai_${ENVIRONMENT}_*.sql | tail -n +11 | xargs -r rm
        else
            echo -e "${YELLOW}Warning: Backup file is empty or not created.${NC}"
        fi
    else
        echo -e "${YELLOW}Skipping database backup.${NC}"
    fi
}

# Function to deploy
deploy() {
    echo -e "\n${YELLOW}Deploying to $ENVIRONMENT...${NC}"
    
    cd "$PROJECT_ROOT"
    
    # Pull latest images for dependencies
    docker compose -f "$COMPOSE_FILE" pull postgres redis nginx 2>/dev/null || true
    
    # Deploy with docker compose
    if [[ -f "$ENV_FILE" ]]; then
        docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d --remove-orphans
    else
        docker compose -f "$COMPOSE_FILE" up -d --remove-orphans
    fi
    
    # Wait for services to be healthy
    echo "Waiting for services to be healthy..."
    sleep 10
    
    # Check health
    for i in {1..30}; do
        if curl -f http://localhost:8501/_stcore/health > /dev/null 2>&1; then
            echo -e "${GREEN}Application is healthy!${NC}"
            break
        fi
        echo "Waiting for application... ($i/30)"
        sleep 2
    done
    
    if ! curl -f http://localhost:8501/_stcore/health > /dev/null 2>&1; then
        echo -e "${RED}Application health check failed!${NC}"
        docker compose -f "$COMPOSE_FILE" logs --tail=50
        exit 1
    fi
    
    echo -e "${GREEN}Deployment successful!${NC}"
}

# Function to rollback
rollback() {
    echo -e "\n${YELLOW}Rolling back $ENVIRONMENT...${NC}"
    
    cd "$PROJECT_ROOT"
    
    # Get previous image tag
    PREVIOUS_TAG=$(docker images --format "{{.Repository}}:{{.Tag}}" | grep "geneai-research:${ENVIRONMENT}-" | head -2 | tail -1)
    
    if [[ -z "$PREVIOUS_TAG" ]]; then
        echo -e "${RED}No previous image found for rollback!${NC}"
        exit 1
    fi
    
    echo "Rolling back to: $PREVIOUS_TAG"
    
    # Tag as latest for this environment
    docker tag "$PREVIOUS_TAG" "geneai-research:${ENVIRONMENT}-latest"
    
    # Redeploy
    docker compose -f "$COMPOSE_FILE" up -d --remove-orphans
    
    # Wait and check health
    sleep 10
    if curl -f http://localhost:8501/_stcore/health > /dev/null 2>&1; then
        echo -e "${GREEN}Rollback successful!${NC}"
    else
        echo -e "${RED}Rollback failed!${NC}"
        exit 1
    fi
}

# Function to backup
backup() {
    echo -e "\n${YELLOW}Creating backup for $ENVIRONMENT...${NC}"
    
    BACKUP_DIR="$PROJECT_ROOT/backups/$ENVIRONMENT"
    mkdir -p "$BACKUP_DIR"
    
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    BACKUP_FILE="$BACKUP_DIR/geneai_${ENVIRONMENT}_${TIMESTAMP}.sql"
    
    docker compose -f "$PROJECT_ROOT/$COMPOSE_FILE" exec -T postgres pg_dump -U geneai geneai > "$BACKUP_FILE"
    
    if [[ -f "$BACKUP_FILE" && -s "$BACKUP_FILE" ]]; then
        echo -e "${GREEN}Backup created: $BACKUP_FILE${NC}"
    else
        echo -e "${RED}Backup failed!${NC}"
        exit 1
    fi
}

# Function to restore
restore() {
    echo -e "\n${YELLOW}Restoring backup for $ENVIRONMENT...${NC}"
    
    BACKUP_DIR="$PROJECT_ROOT/backups/$ENVIRONMENT"
    
    if [[ ! -d "$BACKUP_DIR" ]]; then
        echo -e "${RED}Backup directory not found: $BACKUP_DIR${NC}"
        exit 1
    fi
    
    # List available backups
    echo "Available backups:"
    ls -lt "$BACKUP_DIR"/geneai_${ENVIRONMENT}_*.sql | head -10
    
    read -p "Enter backup filename to restore (or 'latest'): " BACKUP_NAME
    
    if [[ "$BACKUP_NAME" == "latest" ]]; then
        BACKUP_FILE=$(ls -t "$BACKUP_DIR"/geneai_${ENVIRONMENT}_*.sql | head -1)
    else
        BACKUP_FILE="$BACKUP_DIR/$BACKUP_NAME"
    fi
    
    if [[ ! -f "$BACKUP_FILE" ]]; then
        echo -e "${RED}Backup file not found: $BACKUP_FILE${NC}"
        exit 1
    fi
    
    read -p "This will overwrite the current database. Are you sure? (yes/no): " CONFIRM
    if [[ "$CONFIRM" != "yes" ]]; then
        echo "Restore cancelled."
        exit 0
    fi
    
    echo "Restoring from: $BACKUP_FILE"
    
    # Stop app to prevent connections
    docker compose -f "$PROJECT_ROOT/$COMPOSE_FILE" stop app
    
    # Restore database
    docker compose -f "$PROJECT_ROOT/$COMPOSE_FILE" exec -T postgres psql -U geneai -d geneai < "$BACKUP_FILE"
    
    # Restart app
    docker compose -f "$PROJECT_ROOT/$COMPOSE_FILE" start app
    
    echo -e "${GREEN}Restore completed!${NC}"
}

# Main execution
main() {
    pre_deployment_checks
    
    case $ACTION in
        deploy)
            run_tests
            build_image
            backup_database
            deploy
            ;;
        rollback)
            rollback
            ;;
        backup)
            backup
            ;;
        restore)
            restore
            ;;
    esac
    
    echo -e "\n${BLUE}========================================${NC}"
    echo -e "${GREEN}Operation completed successfully!${NC}"
    echo -e "${BLUE}========================================${NC}"
}

main "$@"
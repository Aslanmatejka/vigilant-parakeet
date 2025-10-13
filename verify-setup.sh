#!/bin/bash

# DoGoods App Setup Verification Script
# This script verifies that the project is properly set up and ready for development

set -e

echo "🔍 Verifying DoGoods App setup..."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    if [ $2 -eq 0 ]; then
        echo -e "${GREEN}✅ $1${NC}"
    else
        echo -e "${RED}❌ $1${NC}"
        exit 1
    fi
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

# Check if we're in the right directory
if [ ! -f "package.json" ]; then
    echo -e "${RED}❌ Error: package.json not found. Please run this script from the project root.${NC}"
    exit 1
fi

echo "📁 Checking project structure..."

# Check essential directories
directories=("components" "pages" "utils" "styles" "supabase" "tests" "scripts")
for dir in "${directories[@]}"; do
    if [ -d "$dir" ]; then
        print_status "Directory $dir exists" 0
    else
        print_status "Directory $dir exists" 1
    fi
done

# Check essential files
files=("app.jsx" "vite.config.js" "tailwind.config.js" "index.html" "README.md")
for file in "${files[@]}"; do
    if [ -f "$file" ]; then
        print_status "File $file exists" 0
    else
        print_status "File $file exists" 1
    fi
done

echo "📦 Checking dependencies..."

# Check if node_modules exists
if [ -d "node_modules" ]; then
    print_status "Dependencies installed" 0
else
    print_warning "Dependencies not installed. Run 'npm install' first."
    exit 1
fi

# Check if key packages are installed
if [ -d "node_modules/react" ]; then
    print_status "React is installed" 0
else
    print_status "React is installed" 1
fi

if [ -d "node_modules/@supabase/supabase-js" ]; then
    print_status "Supabase client is installed" 0
else
    print_status "Supabase client is installed" 1
fi

echo "🔧 Checking configuration files..."

# Check Supabase config
if [ -f "supabase/config.toml" ]; then
    print_status "Supabase configuration exists" 0
else
    print_status "Supabase configuration exists" 1
fi

# Check environment example
if [ -f "config/env.example" ]; then
    print_status "Environment example file exists" 0
else
    print_status "Environment example file exists" 1
fi

echo "🏗️  Testing build process..."

# Test if the application builds
if npm run build > /dev/null 2>&1; then
    print_status "Application builds successfully" 0
else
    print_status "Application builds successfully" 1
fi

# Check if dist directory was created
if [ -d "dist" ]; then
    print_status "Build output directory created" 0
else
    print_status "Build output directory created" 1
fi

echo "🧪 Checking test setup..."

# Check if Jest is configured
if [ -f "jest.config.js" ]; then
    print_status "Jest configuration exists" 0
else
    print_status "Jest configuration exists" 1
fi

# Check if test setup file exists
if [ -f "tests/setup.js" ]; then
    print_status "Test setup file exists" 0
else
    print_status "Test setup file exists" 1
fi

echo "🐳 Checking Docker setup..."

# Check Docker files
if [ -f "Dockerfile" ]; then
    print_status "Dockerfile exists" 0
else
    print_status "Dockerfile exists" 1
fi

if [ -f "docker-compose.yml" ]; then
    print_status "Docker Compose file exists" 0
else
    print_status "Docker Compose file exists" 1
fi

if [ -f "nginx.conf" ]; then
    print_status "Nginx configuration exists" 0
else
    print_status "Nginx configuration exists" 1
fi

echo "🚀 Checking deployment setup..."

# Check deployment script
if [ -f "deploy.sh" ] && [ -x "deploy.sh" ]; then
    print_status "Deployment script exists and is executable" 0
else
    print_status "Deployment script exists and is executable" 1
fi

# Check GitHub Actions
if [ -d ".github/workflows" ] && [ -f ".github/workflows/ci-cd.yml" ]; then
    print_status "GitHub Actions workflow exists" 0
else
    print_status "GitHub Actions workflow exists" 1
fi

echo ""
echo "🎉 Setup verification completed!"
echo ""
echo "📋 Next steps:"
echo "1. Copy config/env.example to .env.local and configure your Supabase credentials"
echo "2. Run 'npm run supabase:start' to start local Supabase (optional)"
echo "3. Run 'npm run dev' to start the development server"
echo "4. Open http://localhost:3001 in your browser"
echo ""
echo "🚀 For deployment:"
echo "- Run './deploy.sh' for deployment options"
echo "- Use Docker: 'docker-compose up'"
echo "- Use GitHub Actions for CI/CD"
echo ""
echo "📚 Check README.md for detailed documentation" 
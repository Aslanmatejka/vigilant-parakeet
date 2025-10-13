#!/bin/bash

# DoGoods App Deployment Script
# This script handles building and deploying the application

set -e

echo "🚀 Starting DoGoods App deployment..."

# Check if we're in the right directory
if [ ! -f "package.json" ]; then
    echo "❌ Error: package.json not found. Please run this script from the project root."
    exit 1
fi

# Install dependencies if node_modules doesn't exist
if [ ! -d "node_modules" ]; then
    echo "📦 Installing dependencies..."
    npm install
fi

# Run tests
echo "🧪 Running tests..."
npm test

# Build the application
echo "🔨 Building application..."
npm run build

# Check if build was successful
if [ ! -d "dist" ]; then
    echo "❌ Build failed. dist directory not found."
    exit 1
fi

echo "✅ Build completed successfully!"

# Check if we should deploy to a specific platform
if [ "$1" = "vercel" ]; then
    echo "🚀 Deploying to Vercel..."
    if command -v vercel &> /dev/null; then
        vercel --prod
    else
        echo "❌ Vercel CLI not found. Please install it first: npm i -g vercel"
        exit 1
    fi
elif [ "$1" = "netlify" ]; then
    echo "🚀 Deploying to Netlify..."
    if command -v netlify &> /dev/null; then
        netlify deploy --prod --dir=dist
    else
        echo "❌ Netlify CLI not found. Please install it first: npm i -g netlify-cli"
        exit 1
    fi
elif [ "$1" = "firebase" ]; then
    echo "🚀 Deploying to Firebase..."
    if command -v firebase &> /dev/null; then
        firebase deploy
    else
        echo "❌ Firebase CLI not found. Please install it first: npm i -g firebase-tools"
        exit 1
    fi
else
    echo "📁 Build ready for deployment!"
    echo "Available deployment options:"
    echo "  ./deploy.sh vercel    - Deploy to Vercel"
    echo "  ./deploy.sh netlify   - Deploy to Netlify"
    echo "  ./deploy.sh firebase  - Deploy to Firebase"
    echo ""
    echo "Or manually upload the 'dist' folder to your hosting provider."
fi

echo "🎉 Deployment process completed!" 
#!/bin/bash

# Check if mvn is installed
if ! command -v mvn &> /dev/null
then
    echo "Maven (mvn) could not be found. Please install it to build the project."
    exit 1
fi

echo "Building Realm Info Mapper..."
mvn clean package

if [ $? -eq 0 ]; then
    echo "Build successful! JAR file is located in target/realm-info-mapper.jar"
else
    echo "Build failed."
    exit 1
fi

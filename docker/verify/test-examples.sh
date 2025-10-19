#!/bin/bash
# Example usage scenarios for the enhanced test-transcription.sh script

set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${BLUE}MxWhisper API Test Examples${NC}"
echo ""

# Make sure we have a token
if [[ -z "$AUTH_TOKEN" ]]; then
    echo -e "${YELLOW}Note: Set AUTH_TOKEN environment variable or use --token flag${NC}"
    echo ""
fi

echo -e "${GREEN}Example 1: Basic Transcription${NC}"
echo "  ./test-transcription.sh audio.mp3"
echo ""

echo -e "${GREEN}Example 2: With Custom API URL and Token${NC}"
echo "  ./test-transcription.sh audio.mp3 --url http://api.example.com --token YOUR_TOKEN"
echo ""

echo -e "${GREEN}Example 3: Assign Topics During Upload${NC}"
echo "  # Assign to \"Sermons\" (ID 6) and \"Religious\" (ID 1) topics"
echo "  ./test-transcription.sh sermon.mp3 --topic-ids 6,1"
echo ""

echo -e "${GREEN}Example 4: Create and Add to Collection${NC}"
echo "  # Creates 'Sunday Sermons' collection if it doesn't exist"
echo "  ./test-transcription.sh sermon1.mp3 --collection \"Sunday Sermons\""
echo ""

echo -e "${GREEN}Example 5: Add to Collection with Position${NC}"
echo "  # Add as chapter 1 in a book collection"
echo "  ./test-transcription.sh chapter1.mp3 --collection \"Romans Study\" --position 1"
echo "  ./test-transcription.sh chapter2.mp3 --collection \"Romans Study\" --position 2"
echo ""

echo -e "${GREEN}Example 6: Full Workflow - Topics + Collection${NC}"
echo "  # Assign topics AND add to collection with position"
echo "  ./test-transcription.sh lecture1.mp3 \\"
echo "    --topic-ids 10,11 \\"
echo "    --collection \"Python Course\" \\"
echo "    --position 1"
echo ""

echo -e "${GREEN}Example 7: Batch Upload Multiple Files to Collection${NC}"
echo "  # Upload an entire book/course series"
echo "  for i in {1..12}; do"
echo "    ./test-transcription.sh \"chapter\$i.mp3\" \\"
echo "      --collection \"Complete Romans Study\" \\"
echo "      --topic-ids 5 \\"
echo "      --position \$i"
echo "  done"
echo ""

echo -e "${BLUE}Available Topic IDs (from seed data):${NC}"
echo "  Root Topics:"
echo "    1  - Religious"
echo "    2  - Educational"
echo "    3  - Entertainment"
echo "    4  - Professional"
echo ""
echo "  Religious Subcategories:"
echo "    5  - Bible Study"
echo "    6  - Sermons"
echo "    7  - Prayer"
echo "    8  - Worship"
echo "    9  - Theology"
echo ""
echo "  Educational Subcategories:"
echo "    10 - Courses"
echo "    11 - Tutorials"
echo "    12 - Conferences"
echo "    13 - Lectures"
echo ""
echo "  Entertainment Subcategories:"
echo "    14 - Podcasts"
echo "    15 - Audiobooks"
echo "    16 - Interviews"
echo "    17 - Music"
echo ""
echo "  Professional Subcategories:"
echo "    18 - Meetings"
echo "    19 - Presentations"
echo "    20 - Webinars"
echo ""

echo -e "${BLUE}Tip:${NC} To view all topics via API:"
echo "  curl -s http://localhost:8000/topics | jq"
echo ""

echo -e "${BLUE}Tip:${NC} To view your collections:"
echo "  curl -s -H \"Authorization: Bearer \$AUTH_TOKEN\" http://localhost:8000/collections | jq"
echo ""

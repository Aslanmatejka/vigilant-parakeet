import React from 'react';
import { useNavigate } from "react-router-dom";
import Card from "../components/common/Card";
import Button from "../components/common/Button";
import Avatar from "../components/common/Avatar";
import ErrorBoundary from "../components/common/ErrorBoundary";
import { useImpact } from "../utils/hooks/useImpact";
import supabase from "../utils/supabaseClient";

function SuccessContent() {
    const navigate = useNavigate();
    const { impact, loading: impactLoading } = useImpact();
    const [activeUsers, setActiveUsers] = React.useState(0);

    React.useEffect(() => {
        fetchActiveUsers();
    }, []);

    const fetchActiveUsers = async () => {
        const { data } = await supabase.from('users').select('id', { count: 'exact' });
        setActiveUsers(data?.length || 0);
    };
    const stories = [
        {
            id: 1,
            title: "Local Restaurant's Food Rescue Initiative",
            description: "How a small restaurant made a big impact by donating surplus food...",
            impact: {
                meals: 1500,
                waste: 750,
                co2: 1200
            },
            image: "https://images.unsplash.com/photo-1498837167922-ddd27525d352",
            author: {
                name: "John Smith",
                role: "Restaurant Owner",
                avatar: "https://randomuser.me/api/portraits/men/2.jpg"
            }
        },
        // Add more success stories...
    ];

    const stats = {
        totalMeals: impact.totalMeals,
        wasteReduced: impact.wasteReduced,
        co2Saved: impact.co2Saved,
        activeUsers: activeUsers
    };

    const handleReadFullStory = (storyId) => {
                    navigate(`/success/${storyId}`);
    };

    const handleSubmitStory = () => {
                    navigate('/success/submit');
    };

    return (
        <div data-name="success-stories" className="max-w-7xl mx-auto py-12 px-4">
            <div className="text-center mb-16">
                <h1 className="text-4xl font-bold text-gray-900 mb-4">
                    Success Stories
                </h1>
                <p className="text-xl text-gray-600">
                    Real impact stories from our community members
                </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-16" role="list" aria-label="Impact Statistics">
                <div role="listitem">
                    <Card>
                        <div className="text-center p-6">
                            <div className="text-3xl font-bold text-green-600">
                                {stats.totalMeals.toLocaleString()}
                            </div>
                            <div className="text-sm text-gray-600">Meals Shared</div>
                        </div>
                    </Card>
                </div>
                <div role="listitem">
                    <Card>
                        <div className="text-center p-6">
                            <div className="text-3xl font-bold text-green-600">
                                {stats.wasteReduced.toLocaleString()}kg
                            </div>
                            <div className="text-sm text-gray-600">Food Waste Reduced</div>
                        </div>
                    </Card>
                </div>
                <div role="listitem">
                    <Card>
                        <div className="text-center p-6">
                            <div className="text-3xl font-bold text-green-600">
                                {stats.co2Saved.toLocaleString()}kg
                            </div>
                            <div className="text-sm text-gray-600">CO2 Emissions Saved</div>
                        </div>
                    </Card>
                </div>
                <div role="listitem">
                    <Card>
                        <div className="text-center p-6">
                            <div className="text-3xl font-bold text-green-600">
                                {stats.activeUsers.toLocaleString()}+
                            </div>
                            <div className="text-sm text-gray-600">Active Members</div>
                        </div>
                    </Card>
                </div>
            </div>

            <div className="space-y-12" role="feed" aria-label="Success Stories">
                {stories.map((story) => (
                    <article key={story.id} role="article">
                        <Card className="overflow-hidden">
                            <div className="md:flex">
                                <div className="md:flex-shrink-0">
                                    <img
                                        className="h-48 w-full object-cover md:h-full md:w-48"
                                        src={story.image}
                                        alt={`${story.title} featured image`}
                                        loading="lazy"
                                    />
                                </div>
                                <div className="p-8">
                                    <div className="flex items-center justify-between mb-4">
                                        <h2 className="text-2xl font-bold text-gray-900">
                                            {story.title}
                                        </h2>
                                        <div className="flex items-center space-x-2">
                                            <Avatar
                                                src={story.author.avatar}
                                                size="md"
                                                alt={`${story.author.name}'s avatar`}
                                            />
                                            <div>
                                                <div className="font-medium">
                                                    {story.author.name}
                                                </div>
                                                <div className="text-sm text-gray-500">
                                                    {story.author.role}
                                                </div>
                                            </div>
                                        </div>
                                    </div>

                                    <p className="text-gray-600 mb-6">
                                        {story.description}
                                    </p>

                                    <div className="grid grid-cols-3 gap-4 mb-6" role="list" aria-label="Impact Metrics">
                                        <div role="listitem" className="text-center p-4 bg-green-50 rounded-lg">
                                            <div className="font-bold text-green-600">
                                                {story.impact.meals.toLocaleString()}
                                            </div>
                                            <div className="text-sm text-gray-600">
                                                Meals Shared
                                            </div>
                                        </div>
                                        <div role="listitem" className="text-center p-4 bg-green-50 rounded-lg">
                                            <div className="font-bold text-green-600">
                                                {story.impact.waste.toLocaleString()}kg
                                            </div>
                                            <div className="text-sm text-gray-600">
                                                Waste Reduced
                                            </div>
                                        </div>
                                        <div role="listitem" className="text-center p-4 bg-green-50 rounded-lg">
                                            <div className="font-bold text-green-600">
                                                {story.impact.co2.toLocaleString()}kg
                                            </div>
                                            <div className="text-sm text-gray-600">
                                                CO2 Saved
                                            </div>
                                        </div>
                                    </div>

                                    <Button 
                                        variant="primary"
                                        onClick={() => handleReadFullStory(story.id)}
                                        aria-label={`Read full story about ${story.title}`}
                                    >
                                        Read Full Story
                                    </Button>
                                </div>
                            </div>
                        </Card>
                    </article>
                ))}
            </div>

            <div className="text-center mt-12">
                <h2 className="text-3xl font-bold text-gray-900 mb-6">
                    Share Your Success Story
                </h2>
                <p className="text-gray-600 mb-8 max-w-2xl mx-auto">
                    Have you made an impact in your community through ShareFoods?
                    We'd love to hear your story and share it with others.
                </p>
                <Button
                    variant="primary"
                    size="lg"
                    onClick={handleSubmitStory}
                    icon={<i className="fas fa-pen" aria-hidden="true"></i>}
                >
                    Submit Your Story
                </Button>
            </div>
        </div>
    );
}

function Success() {
    return (
        <ErrorBoundary>
            <SuccessContent />
        </ErrorBoundary>
    );
}

export default Success;

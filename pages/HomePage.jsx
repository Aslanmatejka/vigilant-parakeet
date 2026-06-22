import { useNavigate } from "react-router-dom";
import React from "react";
import Card from "../components/common/Card";
import Button from "../components/common/Button";
import ErrorBoundary from "../components/common/ErrorBoundary";
import HeroSlideshow from "../components/common/HeroSlideshow";
import { reportError } from "../utils/helpers";
import { DonateVolunteerButtons } from "./CommunityPage";
import communitiesStatic from '../utils/communities';
import supabase from "../utils/supabaseClient";

function HomePage() {
    const navigate = useNavigate();
    const [communities, setCommunities] = React.useState([]);
    const [loadingCommunities, setLoadingCommunities] = React.useState(true);
    const [selectedLocation, setSelectedLocation] = React.useState('all');
    const [showAllCommunities, setShowAllCommunities] = React.useState(false);
    
    // Fetch communities with their metrics from database
    React.useEffect(() => {
        const fetchCommunities = async () => {
            try {
                const { data, error } = await supabase
                    .from('communities')
                    .select('*')
                    .eq('is_active', true);
                
                if (error) throw error;
                
                // Merge database data with static data for images/location/contact/hours
                const mergedCommunities = (data || []).map(dbCommunity => {
                    const staticCommunity = communitiesStatic.find(c => c.name === dbCommunity.name);
                    return {
                        ...staticCommunity,
                        ...dbCommunity,
                        // Ensure static fields are preserved or use defaults
                        image: staticCommunity?.image || dbCommunity.image || 'https://images.unsplash.com/photo-1559027615-cd4628902d4a?w=800&h=600&fit=crop',
                        location: staticCommunity?.location || dbCommunity.location || 'Location TBD',
                        contact: staticCommunity?.contact || dbCommunity.contact || 'Contact TBD',
                        hours: staticCommunity?.hours || dbCommunity.hours || 'Hours TBD'
                    };
                });
                
                setCommunities(mergedCommunities);
            } catch (error) {
                console.error('Error fetching communities:', error);
                reportError(error);
                // Fallback to static data
                setCommunities(communitiesStatic);
            } finally {
                setLoadingCommunities(false);
            }
        };
        
        fetchCommunities();
    }, []);
    
    // Filter communities by location
    const filteredCommunities = React.useMemo(() => {
        if (selectedLocation === 'all') {
            return communities;
        }
        
        const locationMap = {
            'alameda': ['Do Good Warehouse', 'Encinal Jr Sr High School', 'Island HS CC', 'NEA/ACLC CC', 'Academy of Alameda CC', 'Ruby Bridges Elementary CC'],
            'oakland': ['McClymonds High School', 'Markham Elementary', 'Madison Park Academy', 'Madison Park Academy Primary', 'Garfield Elementary', 'Lodestar Charter School', 'Horace Mann Elementary'],
            'san-lorenzo': ['Hillside Elementary School', 'Edendale Middle School', 'San Lorenzo High School']
        };
        
        const communityNames = locationMap[selectedLocation] || [];
        return communities.filter(c => communityNames.includes(c.name));
    }, [communities, selectedLocation]);
    
    try {
        return (
            <ErrorBoundary>
                <div data-name="home-page" role="main">
                    {/* Hero Section with Slideshow Background */}
                    <HeroSlideshow>
                        <section 
                            className="py-14 sm:py-20 md:py-24"
                            aria-labelledby="hero-heading"
                        >
                            <div className="container mx-auto px-4">
                                <div className="max-w-3xl mx-auto text-center">
                                    <h1 
                                        id="hero-heading"
                                        className="text-3xl sm:text-4xl md:text-5xl font-bold mb-4 sm:mb-6 text-white drop-shadow-lg"
                                    >
                                        Find Food, Reduce Waste, Build Community
                                    </h1>
                                    <p className="text-lg sm:text-xl mb-0 text-white drop-shadow-md">
                                        Join our movement to combat food waste and hunger through community-driven food sharing.
                                    </p>
                                    {/* <div className="flex gap-6 justify-center items-center max-w-4xl mx-auto">
                                        <button 
                                            onClick={() => handleNavigation('/find')}
                                            aria-label="Find food in your area"
                                            className="flex-1 px-12 py-8 text-2xl md:text-3xl font-bold bg-[#2CABE3] text-white rounded-2xl shadow-2xl hover:opacity-90 hover:scale-105 transition-all duration-300 transform"
                                        >
                                            <i className="fas fa-search mr-3"></i>
                                            Find Food
                                        </button>
                                        <button 
                                            onClick={() => handleNavigation('/share')}
                                            aria-label="Share food with the community"
                                            className="flex-1 px-12 py-8 text-2xl md:text-3xl font-bold bg-[#171366] text-white rounded-2xl shadow-2xl hover:opacity-90 hover:scale-105 transition-all duration-300 transform"
                                        >
                                            <i className="fas fa-share-alt mr-3"></i>
                                            Share Food
                                        </button>
                                    </div> */}
                                </div>
                            </div>
                        </section>
                    </HeroSlideshow>

                    {/* How It Works Schematic */}
                    {/* <section
                        className="py-16 bg-gray-50"
                        aria-labelledby="how-it-works-schematic-heading"
                    >
                        <div className="container mx-auto px-4">
                            <div className="text-center mb-12">
                                <h2
                                    id="how-it-works-schematic-heading"
                                    className="text-3xl font-bold text-gray-900 mb-4"
                                >
                                    How It Works
                                </h2>
                                <p className="text-xl text-gray-600">
                                    Join our community in three simple steps
                                </p>
                            </div>

                            <div className="max-w-5xl mx-auto">
                                <div className="relative">
                                    <div className="grid grid-cols-1 md:grid-cols-3 gap-8 relative">
                                        <div className="relative">
                                            <div className="bg-white rounded-lg shadow-lg p-8 text-center h-full flex flex-col items-center justify-center">
                                                <div className="w-20 h-20 bg-primary-100 rounded-full flex items-center justify-center mx-auto mb-4">
                                                    <i className="fas fa-search text-3xl text-primary-600"></i>
                                                </div>
                                                <div className="absolute -top-4 -left-4 w-12 h-12 bg-primary-600 text-white rounded-full flex items-center justify-center text-xl font-bold">
                                                    1
                                                </div>
                                                <h3 className="text-xl font-bold mb-3 text-gray-900">Find Food</h3>
                                                <p className="text-gray-600 mb-4">Browse available food items in your area or search for specific items you need, claim and pick up</p>
                                                <div className="mt-auto pt-4">
                                                    <div className="inline-block bg-primary-50 text-primary-700 text-sm px-4 py-2 rounded-full font-medium">
                                                        Browse Listings
                                                    </div>
                                                </div>
                                            </div>
                                            <div className="hidden md:block absolute top-1/2 -right-4 transform -translate-y-1/2 z-10">
                                                <i className="fas fa-arrow-right text-4xl text-primary-600"></i>
                                            </div>
                                            <div className="md:hidden flex justify-center my-4">
                                                <i className="fas fa-arrow-down text-4xl text-primary-600"></i>
                                            </div>
                                        </div>

                                        <div className="relative">
                                            <div className="bg-white rounded-lg shadow-lg p-8 text-center h-full flex flex-col items-center justify-center">
                                                <div className="w-20 h-20 bg-blue-100 rounded-full flex items-center justify-center mx-auto mb-4">
                                                    <i className="fas fa-comments text-3xl text-blue-600"></i>
                                                </div>
                                                <div className="absolute -top-4 -left-4 w-12 h-12 bg-blue-600 text-white rounded-full flex items-center justify-center text-xl font-bold">
                                                    2
                                                </div>
                                                <h3 className="text-xl font-bold mb-3 text-gray-900">Connect</h3>
                                                <p className="text-gray-600 mb-4">share and claim food through active communities, contact according to active communities and arrange pickups with </p>
                                                <div className="mt-auto pt-4">
                                                    <div className="inline-block bg-blue-50 text-blue-700 text-sm px-4 py-2 rounded-full font-medium">
                                                        Arrange Pickup
                                                    </div>
                                                </div>
                                            </div>
                                            <div className="hidden md:block absolute top-1/2 -right-4 transform -translate-y-1/2 z-10">
                                                <i className="fas fa-arrow-right text-4xl text-blue-600"></i>
                                            </div>
                                            <div className="md:hidden flex justify-center my-4">
                                                <i className="fas fa-arrow-down text-4xl text-blue-600"></i>
                                            </div>
                                        </div>

                                        <div className="relative">
                                            <div className="bg-white rounded-lg shadow-lg p-8 text-center h-full flex flex-col items-center justify-center">
                                                <div className="w-20 h-20 bg-orange-100 rounded-full flex items-center justify-center mx-auto mb-4">
                                                    <i className="fas fa-handshake text-3xl text-orange-600"></i>
                                                </div>
                                                <div className="absolute -top-4 -left-4 w-12 h-12 bg-orange-600 text-white rounded-full flex items-center justify-center text-xl font-bold">
                                                    3
                                                </div>
                                                <h3 className="text-xl font-bold mb-3 text-gray-900">Share & Save</h3>
                                                <p className="text-gray-600 mb-4">share food, and feel in information and wait for confirmation, for it to listed for claim</p>
                                                <div className="mt-auto pt-4">
                                                    <div className="inline-block bg-orange-50 text-orange-700 text-sm px-4 py-2 rounded-full font-medium">
                                                        Make Impact
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                    </div>

                                    <div className="text-center mt-12">
                                        <Button
                                            variant="primary"
                                            size="lg"
                                            onClick={() => handleNavigation('/find')}
                                            aria-label="Start sharing food now"
                                        >
                                            Get Started Now
                                        </Button>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </section> */}

                    {/* Communities Section */}
                    <section 
                        className="py-10 sm:py-16 bg-gray-50"
                        aria-labelledby="communities-heading"
                        data-tutorial="communities-section"
                    >
                        <div className="container mx-auto px-4">
                            <div className="text-center mb-8 sm:mb-12">
                                <h2 
                                    id="communities-heading"
                                    className="text-2xl sm:text-3xl font-bold text-gray-900 mb-3 sm:mb-4"
                                >
                                    Active Communities
                                </h2>
                                <p className="text-base sm:text-xl text-gray-600 mb-6">
                                    Join local food sharing groups in your area
                                </p>
                                
                                {/* Location Filter */}
                                <div className="flex justify-center gap-2 sm:gap-4 flex-wrap">
                                    <button
                                        onClick={() => setSelectedLocation('all')}
                                        className={`px-6 py-2 rounded-lg font-semibold transition-all ${
                                            selectedLocation === 'all'
                                                ? 'bg-[#2CABE3] text-white'
                                                : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
                                        }`}
                                    >
                                        All Locations
                                    </button>
                                    <button
                                        onClick={() => setSelectedLocation('alameda')}
                                        className={`px-6 py-2 rounded-lg font-semibold transition-all ${
                                            selectedLocation === 'alameda'
                                                ? 'bg-[#2CABE3] text-white'
                                                : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
                                        }`}
                                    >
                                        Alameda
                                    </button>
                                    <button
                                        onClick={() => setSelectedLocation('oakland')}
                                        className={`px-6 py-2 rounded-lg font-semibold transition-all ${
                                            selectedLocation === 'oakland'
                                                ? 'bg-[#2CABE3] text-white'
                                                : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
                                        }`}
                                    >
                                        Oakland
                                    </button>
                                    <button
                                        onClick={() => setSelectedLocation('san-lorenzo')}
                                        className={`px-6 py-2 rounded-lg font-semibold transition-all ${
                                            selectedLocation === 'san-lorenzo'
                                                ? 'bg-[#2CABE3] text-white'
                                                : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
                                        }`}
                                    >
                                        San Lorenzo
                                    </button>
                                </div>
                            </div>

                            {loadingCommunities ? (
                                <div className="col-span-full text-center py-8">
                                    <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-[#2CABE3] mx-auto"></div>
                                    <p className="mt-4 text-gray-600">Loading communities...</p>
                                </div>
                            ) : (
                            <>
                            <div 
                                className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6 mb-8 max-w-6xl mx-auto"
                                role="list"
                                aria-label="Active communities"
                            >
                                {(showAllCommunities ? filteredCommunities : filteredCommunities.slice(0, 3)).map((community) => {
                                    // Extract metric values from database
                                    const foodGivenValue = Math.round(parseFloat(community.food_given_lb) || 0);
                                    const familiesHelpedValue = parseInt(community.families_helped) || 0;
                                    const schoolStaffHelpedValue = parseInt(community.school_staff_helped) || 0;
                                    
                                    return (
                                    <Card
                                        key={community.id}
                                        className="overflow-hidden"
                                        role="listitem"
                                        hoverable={true}
                                        onClick={() => navigate(`/community/${community.id}`)}
                                    >
                                        <img
                                            src={community.image}
                                            alt={`${community.name} community`}
                                            className="w-full h-64 object-cover"
                                        />
                                        <div className="p-4">
                                            <h3 className="text-base font-semibold truncate mb-2">{community.name}</h3>
                                            <div className="flex items-start text-xs text-gray-700 mb-1.5">
                                                <i className="fas fa-map-marker-alt w-4 text-center mr-2 mt-0.5 text-gray-500"></i>
                                                <span>{community.location}</span>
                                            </div>
                                            <div className="flex items-start text-xs text-gray-700 mb-1.5">
                                                <i className="fas fa-user w-4 text-center mr-2 mt-0.5 text-gray-500"></i>
                                                <span>Contact: {community.contact}</span>
                                            </div>
                                            <div className="flex items-start text-xs text-gray-700 mb-2">
                                                <i className="fas fa-clock w-4 text-center mr-2 mt-0.5 text-gray-500"></i>
                                                <span>Hours: {community.hours}</span>
                                            </div>

                                            <div className="mt-3 pt-3 border-t space-y-2 bg-blue-50 p-2 rounded">
                                                <div className="flex items-center justify-between text-xs">
                                                    <span className="text-gray-700 font-medium">
                                                        <i className="fas fa-apple-alt text-primary-600 mr-1"></i>
                                                        Food Given (lb)
                                                    </span>
                                                    <span className="text-primary-700 font-bold">{foodGivenValue.toLocaleString()}</span>
                                                </div>
                                                <div className="flex items-center justify-between text-xs">
                                                    <span className="text-gray-700 font-medium">
                                                        <i className="fas fa-users text-blue-600 mr-1"></i>
                                                        Families Helped
                                                    </span>
                                                    <span className="text-blue-700 font-bold">{familiesHelpedValue.toLocaleString()}</span>
                                                </div>
                                                <div className="flex items-center justify-between text-xs">
                                                    <span className="text-gray-700 font-medium">
                                                        <i className="fas fa-chalkboard-teacher text-purple-600 mr-1"></i>
                                                        School Staff Helped
                                                    </span>
                                                    <span className="text-purple-700 font-bold">{schoolStaffHelpedValue.toLocaleString()}</span>
                                                </div>
                                            </div>

                                            <div className="mt-3 pt-2 border-t">
                                                <a href={`tel:${community.phone}`} className="text-sm text-blue-600 hover:underline">
                                                    {community.phone}
                                                </a>
                                            </div>
                                        </div>
                                    </Card>
                                )})}
                            </div>
                            
                            {filteredCommunities.length > 3 && (
                                <div className="text-center mb-8">
                                    <button
                                        onClick={() => setShowAllCommunities(!showAllCommunities)}
                                        className="px-6 py-2 text-white bg-[#2CABE3] hover:bg-[#2398c7] rounded-lg font-semibold transition-colors duration-200"
                                    >
                                        {showAllCommunities ? (
                                            <>
                                                Show Less
                                                <i className="fas fa-chevron-up ml-2" aria-hidden="true"></i>
                                            </>
                                        ) : (
                                            <>
                                                View More Communities
                                                <i className="fas fa-chevron-down ml-2" aria-hidden="true"></i>
                                            </>
                                        )}
                                    </button>
                                </div>
                            )}
                            </>
                            )}
                        </div>
                    </section>

                    {/* Support the Community Section */}
                    <section className="mt-8 mb-10 sm:mt-10 sm:mb-16">
                        <div className="container mx-auto px-4">
                            <h2 className="text-xl sm:text-2xl font-bold mb-4">Support the Community</h2>
                            <DonateVolunteerButtons />
                        </div>
                    </section>


                </div>
            </ErrorBoundary>
        );
    } catch (error) {
        console.error('HomePage error:', error);
        reportError(error);
        return (
            <div className="text-center py-12" role="alert">
                <i className="fas fa-exclamation-circle text-red-500 text-4xl mb-4" aria-hidden="true"></i>
                <h2 className="text-xl font-bold mb-2">Something went wrong</h2>
                <p className="text-gray-600 mb-4">We&apos;re sorry, but there was an error loading this page.</p>
                <Button
                    variant="secondary"
                    onClick={() => window.location.reload()}
                >
                    Reload Page
                </Button>
            </div>
        );
    }
}

export default HomePage;

import React from "react";
import cheeseBoard from "../../pages/sponsoredby/cheese_board.png";
import community from "../../pages/sponsoredby/community.png";
import farm from "../../pages/sponsoredby/farm.png";
import feedingElmeda from "../../pages/sponsoredby/feeding_elmeda.png";
import feelGoodBakery from "../../pages/sponsoredby/feel_good_backery.png";
import shareChicken from "../../pages/sponsoredby/sharechicken.png";
import sharePizza from "../../pages/sponsoredby/sharepizza.png";

const sponsors = [
  { name: "The Cheese Board Collective", img: cheeseBoard },
  { name: "Alameda County Food Bank", img: community },
  { name: "Bakery", img: farm },
  { name: "Alameda Food Bank", img: feedingElmeda },
  { name: "Feel Good Bakery", img: feelGoodBakery },
  { name: "Community Kitchen", img: shareChicken },
  { name: "Share Pizza", img: sharePizza }
];

function SponsoredBy() {
  return (
    <div className="w-full py-8 px-4 bg-white/70 rounded-2xl shadow-lg flex flex-col items-center mt-10">
      <h2 className="text-2xl font-bold text-green-700 mb-6">Sponsored By</h2>
      <div className="flex flex-wrap justify-center gap-8">
        {sponsors.map((sponsor) => (
          <div key={sponsor.name} className="flex flex-col items-center">
            <img
              src={sponsor.img}
              alt={sponsor.name + ' logo'}
              className="h-20 w-20 object-contain rounded-xl shadow-md bg-white/80 border border-green-100 mb-2"
            />
            <span className="text-sm text-gray-700 font-medium">{sponsor.name}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default SponsoredBy;
  

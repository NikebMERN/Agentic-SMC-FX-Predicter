import { useEffect, useState } from "react";
import { fetchPairs } from "../services/api";
import CurrencyCard from "../components/CurrencyCard";
import { useNavigate } from "react-router-dom";
import "../css/Home.css";

function Home() {
    const [pairs, setPairs] = useState([]);
    const [searchTerm, setSearchTerm] = useState("");
    const [loading, setLoading] = useState(true);
    const navigate = useNavigate();

    useEffect(() => {
        const loadPairs = async () => {
            try {
                const data = await fetchPairs();
                setPairs(data.available_files);
            } catch (err) {
                console.error("Failed to load currency pairs:", err);
            } finally {
                setLoading(false);
            }
        };
        loadPairs();
    }, []);

    const filteredPairs = pairs.filter((pair) =>
        pair.toLowerCase().includes(searchTerm.toLowerCase())
    );

    const groupedPairs = filteredPairs.reduce((acc, pair) => {
        const clean = pair.replace("_5min.csv", "");
        const firstLetter = clean[0].toUpperCase();
        if (!acc[firstLetter]) acc[firstLetter] = [];
        acc[firstLetter].push(pair);
        return acc;
    }, {});

    return (
        <div className="home-container">
            <h1 className="home-title">Currency Predictions</h1>
            <input
                type="text"
                placeholder="Search currency pairs..."
                className="search-bar"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
            />

            {loading ? (
                <p className="loading-text">Loading...</p>
            ) : (
                <div className="currency-grid">
                    {Object.keys(groupedPairs)
                        .sort()
                        .map((letter) => (
                            <div key={letter} className="currency-group">
                                <h2 className="group-heading">{letter}</h2>
                                <hr />
                                <div className="group-grid">
                                    {groupedPairs[letter].map((pair) => (
                                        <CurrencyCard
                                            key={pair}
                                            pair={pair}
                                            onClick={() => navigate(`/predict/${pair}`)}
                                        />
                                    ))}
                                </div>
                            </div>
                        ))}
                </div>
            )}
        </div>
    );
}

export default Home;

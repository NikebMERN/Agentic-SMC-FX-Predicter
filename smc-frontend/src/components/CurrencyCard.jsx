import React from "react";
import { motion } from "framer-motion";
import '../css/CurrencyCard.css';

const CurrencyCard = ({ pair, onClick }) => {
  const cleanName = pair.replace('_5min.csv', '');

  return (
    <motion.div
      whileHover={{ scale: 1.05 }}
      whileTap={{ scale: 0.95 }}
      onClick={onClick}
      className="currency-card"
    >
      <div className="card-content">
        <h2>{cleanName}</h2>
      </div>
    </motion.div>
  );
};

export default CurrencyCard;

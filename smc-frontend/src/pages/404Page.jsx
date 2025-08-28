// src/components/NotFound404.jsx
import React from 'react';
import { useNavigate } from 'react-router-dom';
import '../css/NotFound404.css';

const NOTPage = () => {
  const navigate = useNavigate();

  return (
    <div className="notfound-container">
      <div className="notfound-content">
        <h1 className="notfound-title">404</h1>
        <p className="notfound-message">Oops! The page you're looking for doesn't exist.</p>
        <button className="notfound-button" onClick={() => navigate('/')}>
          Go Back Home
        </button>
      </div>
    </div>
  );
};

export default NOTPage;

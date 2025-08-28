import axios from 'axios';

const BASE_URL = 'http://127.0.0.1:5000'; // Adjust if different

export const fetchPairs = async () => {
  const res = await axios.get(`${BASE_URL}/data`);
  return res.data;
};

export const fetchPrediction = async (pair) => {
  const res = await axios.post(`${BASE_URL}/predict`, { filename: pair });
  return res.data;
};

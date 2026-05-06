import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { App } from './App';
import { hydrateFromUrl } from './auth';

hydrateFromUrl();

ReactDOM.createRoot(document.getElementById('root')!).render(
  <BrowserRouter basename="/dashboard">
    <App />
  </BrowserRouter>,
);

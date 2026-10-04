import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './theme.css'

const savedTheme = localStorage.getItem('st_theme')
if (savedTheme) {
  document.documentElement.dataset.theme = savedTheme
} else if (window.matchMedia('(prefers-color-scheme: dark)').matches) {
  document.documentElement.dataset.theme = 'dark'
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)

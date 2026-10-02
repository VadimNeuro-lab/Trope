// Sample clinic data. Every doctor, room and review count is invented.
// SEED drives the generated schedule (see schedule.js), so the same day always
// shows the same open and taken slots.
(function (root) {
  'use strict';

  const SEED = 29;

  const CLINIC = {
    name: 'Linden Clinic',
    visitMinutes: 30,
    bookingDays: 14,
    leadMinutes: 60,
  };

  const SPECIALTIES = [
    { id: 'primary', name: 'Primary care' },
    { id: 'cardiology', name: 'Cardiology' },
    { id: 'dermatology', name: 'Dermatology' },
    { id: 'pediatrics', name: 'Pediatrics' },
    { id: 'orthopedics', name: 'Orthopedics' },
    { id: 'neurology', name: 'Neurology' },
    { id: 'ent', name: 'ENT' },
    { id: 'womens', name: "Women's health" },
  ];

  // days: 0 = Sunday … 6 = Saturday. hours: [start, end) in 24h "HH:MM".
  // Saturdays run 9:00–13:00 for anyone who works them. Lunch is 12:30–13:30.
  const DOCTORS = [
    {
      id: 'maya-thompson', name: 'Dr. Maya Thompson', specialty: 'primary', title: 'Family physician',
      years: 11, rating: 4.9, reviews: 318, languages: ['English', 'Spanish'],
      room: '104', floor: 'Ground floor', days: [1, 2, 3, 4, 5], hours: ['08:30', '16:30'], hue: 168,
    },
    {
      id: 'samuel-okafor', name: 'Dr. Samuel Okafor', specialty: 'primary', title: 'Family physician',
      years: 7, rating: 4.8, reviews: 156, languages: ['English', 'French'],
      room: '106', floor: 'Ground floor', days: [1, 3, 4, 5, 6], hours: ['09:00', '17:00'], hue: 28,
    },
    {
      id: 'elena-park', name: 'Dr. Elena Park', specialty: 'cardiology', title: 'Cardiologist',
      years: 16, rating: 4.9, reviews: 241, languages: ['English', 'Korean'],
      room: '214', floor: '2nd floor', days: [1, 2, 4, 5], hours: ['09:00', '16:00'], hue: 222,
    },
    {
      id: 'rafael-moreno', name: 'Dr. Rafael Moreno', specialty: 'cardiology', title: 'Cardiologist',
      years: 9, rating: 4.7, reviews: 132, languages: ['English', 'Spanish'],
      room: '216', floor: '2nd floor', days: [2, 3, 5, 6], hours: ['10:00', '17:00'], hue: 350,
    },
    {
      id: 'priya-nair', name: 'Dr. Priya Nair', specialty: 'dermatology', title: 'Dermatologist',
      years: 12, rating: 4.9, reviews: 402, languages: ['English', 'Hindi'],
      room: '310', floor: '3rd floor', days: [1, 2, 3, 4], hours: ['09:00', '17:00'], hue: 290,
    },
    {
      id: 'lukas-becker', name: 'Dr. Lukas Becker', specialty: 'dermatology', title: 'Dermatologist',
      years: 6, rating: 4.6, reviews: 88, languages: ['English', 'German'],
      room: '312', floor: '3rd floor', days: [3, 4, 5, 6], hours: ['08:00', '15:00'], hue: 48,
    },
    {
      id: 'hannah-lindqvist', name: 'Dr. Hannah Lindqvist', specialty: 'pediatrics', title: 'Pediatrician',
      years: 14, rating: 5.0, reviews: 276, languages: ['English', 'Swedish'],
      room: '120', floor: 'Ground floor', days: [1, 2, 3, 4, 5], hours: ['08:00', '15:30'], hue: 200,
    },
    {
      id: 'kwame-mensah', name: 'Dr. Kwame Mensah', specialty: 'pediatrics', title: 'Pediatrician',
      years: 8, rating: 4.8, reviews: 190, languages: ['English', 'Twi'],
      room: '122', floor: 'Ground floor', days: [1, 2, 4, 6], hours: ['10:00', '18:00'], hue: 130,
    },
    {
      id: 'sofia-rossi', name: 'Dr. Sofia Rossi', specialty: 'orthopedics', title: 'Orthopedic surgeon',
      years: 18, rating: 4.8, reviews: 165, languages: ['English', 'Italian'],
      room: '402', floor: '4th floor', days: [2, 3, 5], hours: ['09:00', '16:00'], hue: 12,
    },
    {
      id: 'daniel-cho', name: 'Dr. Daniel Cho', specialty: 'neurology', title: 'Neurologist',
      years: 13, rating: 4.7, reviews: 121, languages: ['English', 'Korean'],
      room: '220', floor: '2nd floor', days: [1, 3, 5], hours: ['09:00', '17:00'], hue: 250,
    },
    {
      id: 'amira-haddad', name: 'Dr. Amira Haddad', specialty: 'ent', title: 'ENT specialist',
      years: 10, rating: 4.9, reviews: 143, languages: ['English', 'Arabic', 'French'],
      room: '230', floor: '2nd floor', days: [1, 2, 3, 4, 5], hours: ['08:30', '15:00'], hue: 182,
    },
    {
      id: 'grace-whitfield', name: 'Dr. Grace Whitfield', specialty: 'womens', title: 'OB-GYN',
      years: 15, rating: 4.9, reviews: 287, languages: ['English'],
      room: '140', floor: 'Ground floor', days: [1, 2, 4, 5, 6], hours: ['09:00', '16:30'], hue: 328,
    },
  ];

  const data = { SEED, CLINIC, SPECIALTIES, DOCTORS };
  if (typeof module === 'object' && module.exports) module.exports = data;
  else root.ClinicData = data;
})(typeof window !== 'undefined' ? window : globalThis);

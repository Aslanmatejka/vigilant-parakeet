import React, { createContext, useContext, useReducer } from 'react';

// Initial state
const initialState = {
  claimed: [],    // Goods that have been claimed by the user
  requested: [],  // Goods that have been requested by the user
  loading: false,
  error: null
};

// Action types
const ACTIONS = {
  SET_LOADING: 'SET_LOADING',
  SET_ERROR: 'SET_ERROR',
  SET_CLAIMED_GOODS: 'SET_CLAIMED_GOODS',
  SET_REQUESTED_GOODS: 'SET_REQUESTED_GOODS',
  ADD_CLAIMED_GOOD: 'ADD_CLAIMED_GOOD',
  ADD_REQUESTED_GOOD: 'ADD_REQUESTED_GOOD',
  UPDATE_CLAIM_STATUS: 'UPDATE_CLAIM_STATUS',
  REMOVE_CLAIMED_GOOD: 'REMOVE_CLAIMED_GOOD',
  REMOVE_REQUESTED_GOOD: 'REMOVE_REQUESTED_GOOD'
};

// Reducer function
function goodsReducer(state, action) {
  switch (action.type) {
    case ACTIONS.SET_LOADING:
      return { ...state, loading: action.payload };
    
    case ACTIONS.SET_ERROR:
      return { ...state, error: action.payload };
    
    case ACTIONS.SET_CLAIMED_GOODS:
      return { ...state, claimed: action.payload };
    
    case ACTIONS.SET_REQUESTED_GOODS:
      return { ...state, requested: action.payload };
    
    case ACTIONS.ADD_CLAIMED_GOOD:
      return {
        ...state,
        claimed: [...state.claimed, action.payload]
      };
    
    case ACTIONS.ADD_REQUESTED_GOOD:
      return {
        ...state,
        requested: [...state.requested, action.payload]
      };
    
    case ACTIONS.UPDATE_CLAIM_STATUS:
      return {
        ...state,
        claimed: state.claimed.map(good => 
          good.id === action.payload.id 
            ? { ...good, status: action.payload.status }
            : good
        )
      };
    
    case ACTIONS.REMOVE_CLAIMED_GOOD:
      return {
        ...state,
        claimed: state.claimed.filter(good => good.id !== action.payload)
      };
    
    case ACTIONS.REMOVE_REQUESTED_GOOD:
      return {
        ...state,
        requested: state.requested.filter(good => good.id !== action.payload)
      };
    
    default:
      return state;
  }
}

// Create context
const GoodsContext = createContext();

// Provider component
export function GoodsProvider({ children }) {
  const [state, dispatch] = useReducer(goodsReducer, initialState);

  // Create the value object
  const value = {
    state,
    loading: state.loading,
    error: state.error,
    claimed: state.claimed,
    requested: state.requested,
    
    // Actions
    setLoading: (loading) => 
      dispatch({ type: ACTIONS.SET_LOADING, payload: loading }),
    
    setError: (error) =>
      dispatch({ type: ACTIONS.SET_ERROR, payload: error }),
    
    setClaimed: (goods) =>
      dispatch({ type: ACTIONS.SET_CLAIMED_GOODS, payload: goods }),
    
    setRequested: (goods) =>
      dispatch({ type: ACTIONS.SET_REQUESTED_GOODS, payload: goods }),
    
    addClaimed: (good) =>
      dispatch({ type: ACTIONS.ADD_CLAIMED_GOOD, payload: good }),
    
    addRequested: (good) =>
      dispatch({ type: ACTIONS.ADD_REQUESTED_GOOD, payload: good }),
    
    updateClaimStatus: (id, status) =>
      dispatch({ type: ACTIONS.UPDATE_CLAIM_STATUS, payload: { id, status } }),
    
    removeClaimed: (id) =>
      dispatch({ type: ACTIONS.REMOVE_CLAIMED_GOOD, payload: id }),
    
    removeRequested: (id) =>
      dispatch({ type: ACTIONS.REMOVE_REQUESTED_GOOD, payload: id })
  };

  return (
    <GoodsContext.Provider value={value}>
      {children}
    </GoodsContext.Provider>
  );
}

// Custom hook for using the goods context
export function useGoods() {
  const context = useContext(GoodsContext);
  if (!context) {
    throw new Error('useGoods must be used within a GoodsProvider');
  }
  return context;
}

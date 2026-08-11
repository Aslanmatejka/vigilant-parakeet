/**
 * CSV listing community columns (Jest)
 */
import {
  parseListingsCsv,
  matchCommunityByName,
} from '../utils/csvListings.js';

describe('parseListingsCsv community columns', () => {
  it('keeps per-row community names and ids', () => {
    const csv = [
      'title,quantity,unit,category,community',
      'Apples,5,lbs,produce,School A',
      'Bread,2,loaves,bakery,School B',
      'Rice,10,bags,pantry,1',
    ].join('\n');
    // community_id numeric via community column when digits-only goes to name
    // unless community_id column is used — use both styles:
    const csv2 = [
      'title,quantity,unit,category,community,community_id',
      'Apples,5,lbs,produce,School A,',
      'Bread,2,loaves,bakery,School B,',
      'Rice,10,bags,pantry,,1',
    ].join('\n');
    const { rows, errors } = parseListingsCsv(csv2);
    expect(errors).toEqual([]);
    expect(rows).toHaveLength(3);
    expect(rows[0].community_name).toBe('School A');
    expect(rows[1].community_name).toBe('School B');
    expect(rows[2].community_id).toBe('1');
  });

  it('treats non-numeric community_id as a school name', () => {
    const csv = [
      'title,quantity,unit,category,community_id',
      'Milk,1,gal,dairy,Ruby Bridges',
    ].join('\n');
    const { rows } = parseListingsCsv(csv);
    expect(rows[0].community_name).toBe('Ruby Bridges');
    expect(rows[0].community_id).toBeUndefined();
  });
});

describe('matchCommunityByName', () => {
  const communities = [
    { id: 8, name: 'Alameda High' },
    { id: 12, name: 'Ruby Bridges Elementary' },
    { id: 1, name: 'Do Good Warehouse' },
  ];

  it('matches exact and partial names', () => {
    expect(matchCommunityByName('Alameda High', communities)?.id).toBe(8);
    expect(matchCommunityByName('ruby bridges', communities)?.id).toBe(12);
  });

  it('returns null when unknown', () => {
    expect(matchCommunityByName('Not A Real School', communities)).toBeNull();
  });
});

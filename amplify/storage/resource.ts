import { defineStorage } from "@aws-amplify/backend";


export const imagesStorage = defineStorage({
  name: 'images',
  access: (allow) => ({
    'originals/*': [
      allow.authenticated.to(['write', 'read', 'delete']),
      allow.guest.to(['read'])
    ],
    'json/*': [
      allow.authenticated.to(['write', 'read', 'delete']),
      allow.guest.to(['read'])
    ],
    'geojson/*': [
      allow.authenticated.to(['write', 'read', 'delete']),
      allow.guest.to(['read'])
    ],
     'FM/*': [allow.guest.to(['read'])], 
  })
})
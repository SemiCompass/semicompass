// @media (--tablet)、@media (--pc) を、幅の数値に直す（src/styles/breakpoints.css）
import postcssCustomMedia from 'postcss-custom-media';

export default {
  plugins: [postcssCustomMedia()],
};

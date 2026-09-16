import { makeStyles } from '@material-ui/core';

const useStyles = makeStyles({
  img: {
    height: 70,
    width: 'auto',
    maxWidth: 240,
    objectFit: 'contain',
  },
});

export const LogoFull = () => {
  const classes = useStyles();

  return (
    <img
      className={classes.img}
      src="/logo-resilience-full.png"
      alt="Resilience Cloud"
    />
  );
};
